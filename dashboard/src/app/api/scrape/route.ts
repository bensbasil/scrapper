import { NextResponse } from 'next/server';
import { spawn } from 'child_process';
import path from 'path';

export async function POST(req: Request) {
  try {
    const { category, city, state, country, limit } = await req.json();

    // Construct path to the python script and venv
    const rootDir = path.resolve(process.cwd(), '..');
    const pythonPath = path.join(rootDir, '.venv', 'bin', 'python3');
    const scriptPath = path.join(rootDir, 'pipeline_runner.py');

    // Build arguments
    const args = [scriptPath];
    if (category) args.push('--category', category);
    if (city) args.push('--city', city);
    if (state) args.push('--state', state);
    if (country) args.push('--country', country);
    if (limit) args.push('--limit', limit.toString());

    console.log(`Starting scraper: ${pythonPath} ${args.join(' ')}`);

    // Spawn the process (detached so it keeps running)
    const scraperProcess = spawn(pythonPath, args, {
      cwd: rootDir,
      env: { ...process.env, PYTHONPATH: rootDir }
    });

    scraperProcess.stdout.on('data', (data: Buffer) => console.log(`Scraper Output: ${data.toString()}`));
    scraperProcess.stderr.on('data', (data: Buffer) => console.error(`Scraper Error: ${data.toString()}`));

    return NextResponse.json({ 
      success: true, 
      message: 'Scraper started successfully in the background.' 
    });

  } catch (error: any) {
    console.error('API Error:', error);
    return NextResponse.json({ success: false, error: error.message }, { status: 500 });
  }
}
