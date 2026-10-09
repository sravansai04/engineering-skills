import { z } from 'zod';

export const contactForm = z.object({
  name: z.string().min(1, { message: 'Name is required' }),
  email: z.string().email({ message: 'Enter a valid email address' }),
  message: z.string().max(2000),
});

export type ContactForm = z.infer<typeof contactForm>;
