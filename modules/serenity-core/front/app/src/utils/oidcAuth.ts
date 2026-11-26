import { AuthConfig, AuthUser } from '../types';

const SESSION_KEY = 'serenity_oidc_session';
const PKCE_VERIFIER_KEY = 'serenity_pkce_verifier';
const PKCE_STATE_KEY = 'serenity_pkce_state';

export interface StoredAuthSession {
  idToken: string;
  accessToken: string;
  refreshToken?: string;
  expiresAt: number; // Unix epoch ms
  user: AuthUser;
}

function base64UrlEncode(bytes: Uint8Array): string {
  let binary = '';
  for (let i = 0; i < bytes.length; i += 1) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function generateRandomString(byteLength = 32): string {
  const bytes = new Uint8Array(byteLength);
  crypto.getRandomValues(bytes);
  return base64UrlEncode(bytes);
}

async function generateCodeChallenge(verifier: string): Promise<string> {
  const encoded = new TextEncoder().encode(verifier);
  const digest = await crypto.subtle.digest('SHA-256', encoded);
  return base64UrlEncode(new Uint8Array(digest));
}

export function getRedirectUri(): string {
  return `${window.location.origin}/`;
}

export function decodeJwtPayload(token: string): Record<string, unknown> | null {
  try {
    const parts = token.split('.');
    if (parts.length !== 3) return null;
    const base64 = parts[1].replace(/-/g, '+').replace(/_/g, '/');
    const padded = base64 + '='.repeat((4 - (base64.length % 4)) % 4);
    const json = decodeURIComponent(
      atob(padded)
        .split('')
        .map((c) => `%${`00${c.charCodeAt(0).toString(16)}`.slice(-2)}`)
        .join('')
    );
    return JSON.parse(json) as Record<string, unknown>;
  } catch {
    return null;
  }
}

export function extractUserFromToken(token: string, allowedGroups: string[]): AuthUser {
  const claims = decodeJwtPayload(token) || {};
  const email = typeof claims.email === 'string' ? claims.email : '';
  const username =
    (typeof claims.preferred_username === 'string' && claims.preferred_username) ||
    (typeof claims['cognito:username'] === 'string' && (claims['cognito:username'] as string)) ||
    (typeof claims.name === 'string' && claims.name) ||
    (typeof claims.sub === 'string' && claims.sub) ||
    'Operator';

  const rawGroups = claims['cognito:groups'] ?? claims.groups;
  const groups = Array.isArray(rawGroups)
    ? rawGroups.filter((g): g is string => typeof g === 'string')
    : typeof rawGroups === 'string'
      ? [rawGroups]
      : [];

  const canWrite = allowedGroups.length === 0 || groups.some((g) => allowedGroups.includes(g));

  return {
    identity: email || username,
    email,
    name: (typeof claims.name === 'string' && claims.name) || email || username,
    groups,
    canWrite,
  };
}

export function loadStoredSession(): StoredAuthSession | null {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as StoredAuthSession;
    if (!parsed || !parsed.idToken) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function saveStoredSession(session: StoredAuthSession): void {
  try {
    sessionStorage.setItem(SESSION_KEY, JSON.stringify(session));
  } catch {
    // Ignore storage quota errors
  }
}

export function clearStoredSession(): void {
  try {
    sessionStorage.removeItem(SESSION_KEY);
    sessionStorage.removeItem(PKCE_VERIFIER_KEY);
    sessionStorage.removeItem(PKCE_STATE_KEY);
  } catch {
    // Ignore storage errors
  }
}

export function isSessionValid(session: StoredAuthSession | null): boolean {
  if (!session || !session.idToken) return false;
  return Date.now() < session.expiresAt - 30_000;
}

export async function startOidcLogin(config: AuthConfig): Promise<void> {
  if (!config.authorizationEndpoint || !config.clientId) {
    throw new Error('OIDC authorization endpoint or client ID is missing.');
  }

  const verifier = generateRandomString(48);
  const state = generateRandomString(24);
  const challenge = await generateCodeChallenge(verifier);

  sessionStorage.setItem(PKCE_VERIFIER_KEY, verifier);
  sessionStorage.setItem(PKCE_STATE_KEY, state);

  const params = new URLSearchParams({
    response_type: 'code',
    client_id: config.clientId,
    redirect_uri: getRedirectUri(),
    scope: config.scopes || 'openid email profile',
    state,
    code_challenge: challenge,
    code_challenge_method: 'S256',
  });

  window.location.assign(`${config.authorizationEndpoint}?${params.toString()}`);
}

export async function exchangeAuthorizationCode(
  config: AuthConfig,
  code: string,
  returnedState: string
): Promise<StoredAuthSession> {
  const expectedState = sessionStorage.getItem(PKCE_STATE_KEY);
  const verifier = sessionStorage.getItem(PKCE_VERIFIER_KEY);

  sessionStorage.removeItem(PKCE_STATE_KEY);
  sessionStorage.removeItem(PKCE_VERIFIER_KEY);

  if (!expectedState || returnedState !== expectedState) {
    throw new Error('Invalid OAuth2 state parameter. Please sign in again.');
  }
  if (!verifier) {
    throw new Error('Missing PKCE code verifier. Please sign in again.');
  }
  if (!config.tokenEndpoint) {
    throw new Error('OIDC token endpoint is not configured.');
  }

  const body = new URLSearchParams({
    grant_type: 'authorization_code',
    client_id: config.clientId,
    code,
    redirect_uri: getRedirectUri(),
    code_verifier: verifier,
  });

  const res = await fetch(config.tokenEndpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: body.toString(),
  });

  if (!res.ok) {
    const errText = await res.text().catch(() => '');
    throw new Error(`Token exchange failed (${res.status}): ${errText.slice(0, 160)}`);
  }

  const tokenData = (await res.json()) as {
    id_token?: string;
    access_token?: string;
    refresh_token?: string;
    expires_in?: number;
  };

  const primaryToken = tokenData.id_token || tokenData.access_token || '';
  if (!primaryToken) {
    throw new Error('OIDC provider did not return an ID or access token.');
  }

  const expiresInSec = typeof tokenData.expires_in === 'number' ? tokenData.expires_in : 3600;
  const session: StoredAuthSession = {
    idToken: primaryToken,
    accessToken: tokenData.access_token || primaryToken,
    refreshToken: tokenData.refresh_token,
    expiresAt: Date.now() + expiresInSec * 1000,
    user: extractUserFromToken(primaryToken, config.allowedGroups || []),
  };

  saveStoredSession(session);
  return session;
}

export async function refreshOidcSession(
  config: AuthConfig,
  refreshToken: string
): Promise<StoredAuthSession | null> {
  if (!config.tokenEndpoint || !refreshToken) return null;

  try {
    const body = new URLSearchParams({
      grant_type: 'refresh_token',
      client_id: config.clientId,
      refresh_token: refreshToken,
    });

    const res = await fetch(config.tokenEndpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: body.toString(),
    });
    if (!res.ok) return null;

    const tokenData = (await res.json()) as {
      id_token?: string;
      access_token?: string;
      refresh_token?: string;
      expires_in?: number;
    };
    const primaryToken = tokenData.id_token || tokenData.access_token || '';
    if (!primaryToken) return null;

    const expiresInSec = typeof tokenData.expires_in === 'number' ? tokenData.expires_in : 3600;
    const session: StoredAuthSession = {
      idToken: primaryToken,
      accessToken: tokenData.access_token || primaryToken,
      refreshToken: tokenData.refresh_token || refreshToken,
      expiresAt: Date.now() + expiresInSec * 1000,
      user: extractUserFromToken(primaryToken, config.allowedGroups || []),
    };

    saveStoredSession(session);
    return session;
  } catch {
    return null;
  }
}

export function buildLogoutUrl(config: AuthConfig, idToken?: string): string | null {
  if (!config.logoutEndpoint) return null;

  if (config.mode === 'cognito') {
    const params = new URLSearchParams({
      client_id: config.clientId,
      logout_uri: getRedirectUri(),
    });
    return `${config.logoutEndpoint}?${params.toString()}`;
  }

  const params = new URLSearchParams({
    client_id: config.clientId,
    post_logout_redirect_uri: getRedirectUri(),
  });
  if (idToken) {
    params.set('id_token_hint', idToken);
  }
  return `${config.logoutEndpoint}?${params.toString()}`;
}
