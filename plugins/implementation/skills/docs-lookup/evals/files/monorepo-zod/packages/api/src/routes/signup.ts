export interface SignupRequest {
  body: unknown;
}

export interface SignupResult {
  status: number;
  body: unknown;
}

// TODO: validate the payload before creating the account.
export async function signup(req: SignupRequest): Promise<SignupResult> {
  return { status: 501, body: { error: 'not implemented' } };
}
