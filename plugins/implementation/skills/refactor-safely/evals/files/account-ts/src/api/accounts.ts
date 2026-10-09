import { Router } from "express";
import { DataSource } from "typeorm";
import { Account } from "../models/Account";

// Consumed by the iOS and Android apps. Older app versions stay in use for months.
export function accountsRouter(db: DataSource): Router {
  const router = Router();
  const repo = db.getRepository(Account);

  router.get("/accounts/:id", async (req, res) => {
    const account = await repo.findOneByOrFail({ id: req.params.id });
    res.json(account);
  });

  router.get("/users/:userId/accounts", async (req, res) => {
    const accounts = await repo.findBy({ userId: req.params.userId });
    res.json(accounts);
  });

  return router;
}
