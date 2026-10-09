import { Column, CreateDateColumn, Entity, PrimaryGeneratedColumn } from "typeorm";

// No naming strategy is configured, so each column is named after its property.
@Entity("accounts")
export class Account {
  @PrimaryGeneratedColumn("uuid")
  id!: string;

  @Column()
  userId!: string;

  @Column({ default: "free" })
  plan!: string;

  @CreateDateColumn()
  createdAt!: Date;
}
