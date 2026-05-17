import mysql from 'mysql2/promise';
import dotenv from 'dotenv';

dotenv.config();

export const pool = mysql.createPool({
  host:               process.env.DB_HOST ?? 'localhost',
  port:               Number(process.env.DB_PORT ?? 3306),
  user:               process.env.DB_USER ?? 'root',
  password:           process.env.DB_PASS ?? '',
  database:           process.env.DB_NAME ?? 'racing',
  charset:            'utf8mb4',
  waitForConnections: true,
  connectionLimit:    10,
  queueLimit:         0,
});

// バッチ処理など専有コネクションが必要な場合はこちらを使う
export function createConnection() {
  return pool.getConnection();
}
