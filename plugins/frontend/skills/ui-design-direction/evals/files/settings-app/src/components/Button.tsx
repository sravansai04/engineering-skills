import type { ButtonHTMLAttributes } from 'react';
import './Button.css';

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary';
};

export function Button({ variant = 'primary', className = '', ...rest }: ButtonProps) {
  return <button className={`btn btn--${variant} ${className}`.trim()} {...rest} />;
}
