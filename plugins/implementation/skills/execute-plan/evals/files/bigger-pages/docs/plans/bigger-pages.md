# Plan: bigger pages

Mobile clients make too many round trips. Return more items per page.

## Tasks

T1. Raise the default page size to 50 in `api/listing.py`. Verify: add
    `test_default_returns_50` to `tests/test_listing.py`, and
    `python3 -m unittest discover -s tests -v` passes.

T2. Clamp `page_size` to at most 200. Verify: a test that `page_size=500` returns 200 items
    when 300 exist.

T3. Mention the clamp in README.md.
