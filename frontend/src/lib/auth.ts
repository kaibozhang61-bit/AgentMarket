/**
 * Auth helpers — wraps Cognito SDK for sign-in / sign-out / session.
 *
 * When NEXT_PUBLIC_COGNITO_USER_POOL_ID is empty the helpers fall back to
 * a dev-mode fake-token flow so the frontend works without a real User Pool.
 */

import {
  AuthenticationDetails,
  CognitoUser,
  CognitoUserPool,
  CognitoUserSession,
} from "amazon-cognito-identity-js";

const POOL_ID = process.env.NEXT_PUBLIC_COGNITO_USER_POOL_ID ?? "";
const CLIENT_ID = process.env.NEXT_PUBLIC_COGNITO_CLIENT_ID ?? "";
const TOKEN_KEY = "auth_token";

function getPool(): CognitoUserPool | null {
  if (!POOL_ID || !CLIENT_ID) return null;
  return new CognitoUserPool({ UserPoolId: POOL_ID, ClientId: CLIENT_ID });
}

// ── Sign in ──────────────────────────────────────────────────────────────────

export function signIn(email: string, password: string): Promise<string> {
  const pool = getPool();

  // Dev mode — generate a fake JWT so the backend's dev-decode path works
  if (!pool) {
    const payload = btoa(
      JSON.stringify({ sub: email, email, "cognito:username": email }),
    );
    const fakeToken = `eyJ0eXAiOiJKV1QiLCJhbGciOiJub25lIn0.${payload}.fake`;
    localStorage.setItem(TOKEN_KEY, fakeToken);
    return Promise.resolve(fakeToken);
  }

  return new Promise((resolve, reject) => {
    const user = new CognitoUser({ Username: email, Pool: pool });
    const details = new AuthenticationDetails({
      Username: email,
      Password: password,
    });
    user.authenticateUser(details, {
      onSuccess(session: CognitoUserSession) {
        const token = session.getIdToken().getJwtToken();
        localStorage.setItem(TOKEN_KEY, token);
        resolve(token);
      },
      onFailure(err: Error) {
        reject(err);
      },
    });
  });
}

// ── Session ──────────────────────────────────────────────────────────────────

export function getSession(): Promise<CognitoUserSession | null> {
  const pool = getPool();
  if (!pool) return Promise.resolve(null);
  const user = pool.getCurrentUser();
  if (!user) return Promise.resolve(null);
  return new Promise((resolve) => {
    user.getSession(
      (err: Error | null, session: CognitoUserSession | null) => {
        if (err || !session) return resolve(null);
        // Refresh the stored token
        localStorage.setItem(TOKEN_KEY, session.getIdToken().getJwtToken());
        resolve(session);
      },
    );
  });
}

// ── Helpers ──────────────────────────────────────────────────────────────────

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function isAuthenticated(): boolean {
  return !!getToken();
}

export function signOut(): void {
  localStorage.removeItem(TOKEN_KEY);
  const pool = getPool();
  if (pool) {
    const user = pool.getCurrentUser();
    user?.signOut();
  }
}
