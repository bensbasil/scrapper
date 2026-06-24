import { NextResponse } from 'next/server';
import { spawn } from 'child_process';
import path from 'path';
import { logEmitter } from '@/lib/logEmitter';

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
    if (limit !== undefined && limit !== null) args.push('--limit', limit.toString());

    console.log(`Starting scraper: ${pythonPath} ${args.join(' ')}`);
    
    // Clear history and record startup log
    logEmitter.clearHistory();
    logEmitter.emitLog(`[System] Starting scraper: python3 ${args.slice(1).join(' ')}`);

    // Spawn the process (detached so it keeps running)
    const scraperProcess = spawn(pythonPath, args, {
      cwd: rootDir,
      env: { ...process.env, PYTHONPATH: rootDir }
    });

    const logData = (data: Buffer, isErrorStream: boolean) => {
      const text = data.toString();
      const lines = text.split('\n');
      for (const line of lines) {
        if (!line.trim()) continue;
        let formattedLine = '';
        if (isErrorStream) {
          if (line.includes(' - ERROR - ') || line.includes(' - CRITICAL - ')) {
            formattedLine = `[Scraper ERROR] ${line}`;
            console.error(formattedLine);
          } else if (line.includes(' - WARNING - ')) {
            formattedLine = `[Scraper WARNING] ${line}`;
            console.warn(formattedLine);
          } else if (line.includes(' - INFO - ') || line.includes(' - DEBUG - ')) {
            formattedLine = `[Scraper Output] ${line}`;
            console.log(formattedLine);
          } else {
            // Unexpected stderr output (e.g., Python startup errors, stack traces)
            formattedLine = `[Scraper ERROR] ${line}`;
            console.error(formattedLine);
          }
        } else {
          formattedLine = `[Scraper Output] ${line}`;
          console.log(formattedLine);
        }
        if (formattedLine) {
          logEmitter.emitLog(formattedLine);
        }
      }
    };

    scraperProcess.stdout.on('data', (data: Buffer) => logData(data, false));
    scraperProcess.stderr.on('data', (data: Buffer) => logData(data, true));

    return NextResponse.json({ 
      success: true, 
      message: 'Scraper started successfully in the background.' 
    });

  } catch (error: any) {
    console.error('API Error:', error);
    return NextResponse.json({ success: false, error: error.message }, { status: 500 });
  }
}
