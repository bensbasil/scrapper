import { Pool } from 'pg';

// Use the same DATABASE_URL as the backend
const pool = new Pool({
  connectionString: process.env.DATABASE_URL || 'postgresql://postgres:password@localhost:5432/scraper_db',
});

export const query = (text: string, params?: any[]) => pool.query(text, params);

export default pool;
