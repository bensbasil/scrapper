import { EventEmitter } from 'events';

class LogEmitter extends EventEmitter {
  private static instance: LogEmitter;
  private logHistory: string[] = [];

  private constructor() {
    super();
    this.setMaxListeners(100);
  }

  public static getInstance(): LogEmitter {
    if (!LogEmitter.instance) {
      LogEmitter.instance = new LogEmitter();
    }
    return LogEmitter.instance;
  }

  public emitLog(log: string) {
    this.logHistory.push(log);
    // Keep last 500 lines
    if (this.logHistory.length > 500) {
      this.logHistory.shift();
    }
    this.emit('log', log);
  }

  public getHistory(): string[] {
    return this.logHistory;
  }

  public clearHistory() {
    this.logHistory = [];
  }
}

export const logEmitter = LogEmitter.getInstance();
