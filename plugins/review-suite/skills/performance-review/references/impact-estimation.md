# Estimating Impact

Read this when putting numbers on a finding. An estimate doesn't have to be precise, but it does have to be explicit: state the formula, state the assumptions, give a range, show today's N alongside 10x, and say where it breaks. A wrong but explicit estimate gets corrected in review. A vague "this might be slow" gets ignored.

## The method

1. **Count.** Write how many times the costly operation runs, in terms of N, using the cost sketch from SKILL.md step 3 (e.g. `1 + 2N` round trips, `N x M` comparisons, `rows x row size` bytes).
2. **Price.** Multiply by a unit cost. Use measured numbers from the project when you have them (traces, query logs, benchmarks), and the rough table below when you don't.
3. **Scale by frequency.** Multiply by how often the path runs (requests per second, job runs per day) to get the load added to shared resources such as the database, a downstream API, or memory.
4. **Compare to a budget.** Is the result significant against the endpoint's latency objective, the database's capacity, the pool size, or the memory limit? That comparison sets the severity.
5. **Find the breaking point.** Solve for the N, or the traffic multiple, at which the cost crosses that budget. If the formula is `1 + N` queries at ~1 ms against a 200 ms budget with 50 ms already spent, it breaks near N = 150. Compare that with today's largest customer and the plausible growth. A breaking point the tail already exceeds is a Blocker or High; one at 1000x is usually Low.

## Rough unit costs

These are orders of magnitude for a typical modern server environment. Use them to tell 1 ms from 1 s, not 1.2 ms from 1.5 ms, and replace them with measured numbers whenever you can.

| Operation | Rough cost |
|---|---|
| In-memory hash lookup or comparison | 10-100 ns |
| Main memory reference | ~100 ns |
| Read 1 MB sequentially from memory | ~10-100 µs |
| SSD random read | ~10-200 µs |
| Read 1 MB sequentially from SSD | ~0.2-1 ms |
| Network round trip within one datacenter | ~0.1-1 ms |
| Networked cache get (including the round trip) | ~0.2-1 ms |
| Simple indexed database query (including the round trip) | ~0.5-2 ms |
| New TCP plus TLS connection | 1-3 extra round trips before the first byte |
| Network round trip between regions or continents | ~30-150 ms |
| Third-party API call | ~50-500 ms typical, with multi-second tails |

**Raw compute throughput** for simple operations is roughly 10^8 to 10^9 per second per core in compiled or JIT-compiled code, and roughly 10^7 to 10^8 in interpreted code. So 10^8 comparisons (a quadratic loop over 10,000 items) costs somewhere from a fraction of a second to tens of seconds, depending on the runtime. Either way it's too slow for a request path.

## Little's Law for pools, queues, and concurrency

> Average number in the system = arrival rate x average time in the system  (L = λ x W)

This is the tool for connection pools, worker pools, and thread pools:

- **Connections in use** ≈ (operations per second) × (seconds each operation holds a connection).
- If that number nears the pool size, requests start queuing for a connection. Queuing makes the hold time effectively longer, which raises it further, so latency rises sharply rather than gradually.
- Total across the fleet = pool size × instances (× worker processes per instance). Check it against the database's connection limit.

## Tail latency and amplification

- **Fan-out.** If a request calls k dependencies in parallel and each has a 1% chance of a slow (p99) response, the chance at least one is slow is `1 - 0.99^k`. For k = 10 that is about 9.6%, so the dependency's p99 becomes roughly the caller's p90.
- **Sequential calls** add their latencies, and their tails compound as well.
- **Retries** multiply across layers. With a attempts per layer and d layers, the bottom sees up to `a^d` calls (3 attempts at 3 layers is 27). This happens exactly when the dependency is already failing.

## Worked examples

**N+1 on a list endpoint**
- Pattern: 1 query for the page plus 1 query per row. Page size 50, about 1 ms per query.
- Latency: about +50 ms per request (sequential round trips).
- Load: at 40 requests/s, about 2,040 queries/s instead of 40. The database sees 51 times the query rate.
- At 10x traffic: about 20,400 queries/s from one endpoint. The latency cost is unchanged, but the database is now the risk.

**Transaction held across an HTTP call**
- Before: 200 requests/s, each holding a connection for about 5 ms, gives 1 connection busy on average.
- After: the transaction also spans a payment call with about 300 ms p50 and 2 s p99. On average 200 × 0.3 = 60 connections are busy, and during a slow period with 2 s calls it is 400.
- Budget: 3 instances × a 20-connection pool = 60. The change runs at the pool limit on an average day and exhausts it whenever the dependency slows down. Unrelated endpoints then fail too, because they share the pool. Severity: `critical`.

**Whole-result-set export**
- Pattern: an export loads every matching row into memory before writing the file.
- Size: the largest account has 2 million rows at about 1 KB of raw data each, so 2 GB raw. Language object overhead often multiplies that several times.
- Concurrency: two admins exporting at once doubles it. Memory limit is 1 GB per process.
- Result: an out-of-memory crash for the largest accounts, possibly taking down other requests on the same process. The median account (5,000 rows, about 5 MB) works fine, which is why it passed testing.

**Accidental quadratic matching**
- Pattern: `orders.map(o => users.find(u => u.id === o.userId))`.
- At 500 × 500 that's 250,000 comparisons, which is negligible. Not a finding at today's size.
- If the batch can reach 20,000 × 20,000 (a nightly job for the largest account), that's 4 × 10^8 comparisons: seconds in a JIT runtime and potentially a minute or more if interpreted. That's a finding for the batch path, fixed with a hash map in O(n + m).

## Presenting the estimate

- Show the formula and the inputs: "`1 + N` queries, N ≤ 50, ~1 ms each, so about +50 ms per request".
- Give a range when inputs are uncertain, and name the input that dominates.
- Show 1x and 10x, plus 100x or 1000x when the curve is superlinear, and the tail (largest customer) if skew is plausible.
- State the breaking point in the finding's "Breaks at" line, e.g. "~8k rows per org, which the largest customer already has".
- Label every number as measured or estimated. Don't present a table value as if you had measured it.
- When a finding can't be estimated without data you don't have, say what data would settle it and put it under "Needs measurement" instead of guessing a severity.
