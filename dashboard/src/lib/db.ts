import { Pool } from 'pg';

// Lazy pool instantiation (Phase 5C & 6E):
// Does not throw during build-time module resolution when DATABASE_URL is not set.
// Fails closed at query runtime with an explicit error if DATABASE_URL is missing.
let poolInstance: Pool | null = null;

export function getPool(): Pool {
  if (!poolInstance) {
    if (!process.env.DATABASE_URL) {
      throw new Error(
        "DATABASE_URL environment variable is not set. " +
        "Add it to .env.local (development) or your deployment environment."
      );
    }
    poolInstance = new Pool({
      connectionString: process.env.DATABASE_URL,
    });
  }
  return poolInstance;
}

export const query = (text: string, params?: any[]) => {
  const p = getPool();
  return params !== undefined ? p.query(text, params) : p.query(text);
};

export default getPool;
