import "reflect-metadata";
import { Account } from "../src/models/Account";

test("account serializes with the fields the mobile app reads", () => {
  const account = Object.assign(new Account(), {
    id: "a1",
    userId: "u1",
    plan: "pro",
    createdAt: new Date("2026-01-01T00:00:00Z"),
  });
  expect(JSON.parse(JSON.stringify(account))).toEqual({
    id: "a1",
    userId: "u1",
    plan: "pro",
    createdAt: "2026-01-01T00:00:00.000Z",
  });
});
