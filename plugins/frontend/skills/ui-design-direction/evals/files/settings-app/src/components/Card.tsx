import type { ReactNode } from 'react';
import './Card.css';

type CardProps = {
  title: string;
  description?: string;
  children?: ReactNode;
};

export function Card({ title, description, children }: CardProps) {
  return (
    <section className="card">
      <h2 className="card__title">{title}</h2>
      {description ? <p className="card__description">{description}</p> : null}
      {children}
    </section>
  );
}
