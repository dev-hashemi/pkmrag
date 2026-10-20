/**
 * Mock Obsidian runtime module for Node-based unit testing.
 */

import { createMockEl } from "./mock_dom.js";

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

export class ItemView {
  containerEl: any;
  app: any;

  constructor(leaf?: any) {
    this.containerEl = { children: [createMockEl(), createMockEl()] };
    this.app = leaf?.app ?? {};
  }

  getViewType(): string {
    return "mock-view";
  }

  getDisplayText(): string {
    return "Mock View";
  }

  getIcon(): string {
    return "mock-icon";
  }
}

export class WorkspaceLeaf {
  app: any;

  constructor(app?: any) {
    this.app = app ?? {};
  }
}

export function setIcon(): void {}
export function addIcon(): void {}
