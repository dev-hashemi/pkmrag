/**
 * Mock Obsidian runtime module for Node-based unit testing.
 */

export class Platform {
  static isDesktop = true;
  static isMobile = false;
  static isMacOS = false;
  static isWin = false;
  static isLinux = true;
}

export class Notice {
  constructor(public message: string) {}
}

export class FileSystemAdapter {
  getBasePath(): string {
    return "/home/mockuser/vault";
  }
}

export function setIcon(): void {}
export function addIcon(): void {}
