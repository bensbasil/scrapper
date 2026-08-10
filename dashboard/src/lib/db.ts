import { Pool } from 'pg';

// Sig fix #10: Removed hardcoded fallback connection string.
// If DATABASE_URL is not set the app should fail at startup with a clear
// message — not silently connect using an insecure default password.
if (!process.env.DATABASE_URL) {
  throw new Error(
    "DATABASE_URL environment variable is not set. " +
    "Add it to .env.local (development) or your deployment environment."
  );
}

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
});

export const query = (text: string, params?: any[]) => pool.query(text, params);

export default pool;
