/**
 * CodeMirror 6 Editor Extension: Renders subtle inline indicators next to headings.
 */

import { Extension, RangeSetBuilder } from "@codemirror/state";
import {
  Decoration,
  DecorationSet,
  EditorView,
  ViewPlugin,
  ViewUpdate,
  WidgetType,
} from "@codemirror/view";
import type PkmragPlugin from "./main";

class PkmragHeadingWidget extends WidgetType {
  constructor(
    readonly count: number,
    readonly hasContradiction: boolean,
    readonly onClick: () => void
  ) {
    super();
  }

  toDOM(): HTMLElement {
    const span = document.createElement("span");
    span.className = `pkmrag-inline-indicator ${
      this.hasContradiction ? "pkmrag-inline-warning" : "pkmrag-inline-normal"
    }`;
    span.textContent = this.hasContradiction ? " ⚠️" : " 🔗";
    span.title = `PKMRAG: ${this.count} unlinked connection${
      this.count > 1 ? "s" : ""
    }${this.hasContradiction ? " (includes contradiction)" : ""}. Click to open sidebar.`;


    span.onclick = (e) => {
      e.stopPropagation();
      e.preventDefault();
      this.onClick();
    };

    return span;
  }
}

export function createPkmragEditorExtension(plugin: PkmragPlugin): Extension {
  return ViewPlugin.fromClass(
    class {
      decorations: DecorationSet;

      constructor(view: EditorView) {
        this.decorations = this.buildDecorations(view);
      }

      update(update: ViewUpdate): void {
        if (update.docChanged || update.viewportChanged) {
          this.decorations = this.buildDecorations(update.view);
        }
      }

      private buildDecorations(view: EditorView): DecorationSet {
        if (!plugin.settings.showInlineIndicators) {
          return Decoration.none;
        }

        const activeFile = plugin.app.workspace.getActiveFile();
        if (!activeFile) {
          return Decoration.none;
        }

        const count = plugin.getActiveGapsCount(activeFile.path);
        const hasContra = plugin.hasActiveContradiction(activeFile.path);
        if (count === 0 && !hasContra) {
          return Decoration.none;
        }

        const builder = new RangeSetBuilder<Decoration>();
        let hasDecoratedFirst = false;

        for (const { from, to } of view.visibleRanges) {
          let pos = from;
          while (pos <= to) {
            const line = view.state.doc.lineAt(pos);
            const lineText = line.text;

            // Match Markdown headings (e.g. "# Heading", "## Section")
            if (/^#{1,6}\s+/.test(lineText)) {
              builder.add(
                line.to,
                line.to,
                Decoration.widget({
                  widget: new PkmragHeadingWidget(count, hasContra, () => {
                    plugin.activateView();
                  }),
                  side: 1,
                })
              );
              hasDecoratedFirst = true;
              break; // Only decorate the top heading to avoid visual clutter
            }

            pos = line.to + 1;
          }
          if (hasDecoratedFirst) break;
        }

        return builder.finish();
      }
    },
    {
      decorations: (v) => v.decorations,
    }
  );
}
