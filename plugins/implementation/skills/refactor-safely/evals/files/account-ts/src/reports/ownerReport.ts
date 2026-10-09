import { DataSource } from "typeorm";

export async function accountsPerOwner(db: DataSource): Promise<Array<{ userId: string; count: number }>> {
  const rows = await db.query(
    'SELECT "userId", count(*)::int AS count FROM accounts GROUP BY "userId" ORDER BY count DESC',
  );
  return rows;
}
