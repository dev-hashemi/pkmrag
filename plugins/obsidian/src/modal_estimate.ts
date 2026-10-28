/**
 * Pre-flight Token Estimation & Confirmation Modal for AI Relationship Discovery.
 */

import { App, Modal } from "obsidian";
import { DiscoveryEstimate } from "./types";
import { displayTitle } from "./format";

export interface ModalEstimateParams {
  estimate: DiscoveryEstimate;
  notePath?: string | null;
  noteTitle?: string | null;
  onConfirm: () => Promise<void>;
}

export class DiscoveryEstimateModal extends Modal {
  private params: ModalEstimateParams;

  constructor(app: App, params: ModalEstimateParams) {
    super(app);
    this.params = params;
  }

  onOpen(): void {
    const { contentEl } = this;
    contentEl.empty();
    contentEl.addClass("pkmrag-estimate-modal");

    // Title
    contentEl.createEl("h2", {
      text: "⚡ AI Relationship Discovery",
      cls: "pkmrag-estimate-title",
    });

    const isNote = Boolean(this.params.notePath);
    const scopeLabel = isNote
      ? `Active Note: "${this.params.noteTitle || displayTitle(this.params.notePath!)}"`
      : "Scope: Entire Vault";

    // Scope & Model Info Banner
    const banner = contentEl.createDiv({ cls: "pkmrag-estimate-banner" });
    banner.createDiv({ cls: "pkmrag-estimate-scope", text: scopeLabel });
    const modelTag = banner.createDiv({ cls: "pkmrag-estimate-model" });
    modelTag.createSpan({ cls: "pkmrag-badge", text: `${this.params.estimate.provider} · ${this.params.estimate.model}` });

    // Metric Grid (Token estimations, no dollar costs)
    const grid = contentEl.createDiv({ cls: "pkmrag-estimate-grid" });

    const cardPairs = grid.createDiv({ cls: "pkmrag-estimate-card" });
    cardPairs.createDiv({ cls: "pkmrag-estimate-card-val", text: String(this.params.estimate.evaluated_count) });
    cardPairs.createDiv({ cls: "pkmrag-estimate-card-lbl", text: "Candidate Pairs" });

    const cardPrompt = grid.createDiv({ cls: "pkmrag-estimate-card" });
    cardPrompt.createDiv({
      cls: "pkmrag-estimate-card-val",
      text: this.params.estimate.estimated_prompt_tokens.toLocaleString(),
    });
    cardPrompt.createDiv({ cls: "pkmrag-estimate-card-lbl", text: "Est. Prompt Tokens" });

    const cardComp = grid.createDiv({ cls: "pkmrag-estimate-card" });
    cardComp.createDiv({
      cls: "pkmrag-estimate-card-val",
      text: this.params.estimate.estimated_completion_tokens.toLocaleString(),
    });
    cardComp.createDiv({ cls: "pkmrag-estimate-card-lbl", text: "Est. Completion Tokens" });

    const cardTotal = grid.createDiv({ cls: "pkmrag-estimate-card pkmrag-estimate-card-total" });
    cardTotal.createDiv({
      cls: "pkmrag-estimate-card-val",
      text: this.params.estimate.total_tokens.toLocaleString(),
    });
    cardTotal.createDiv({ cls: "pkmrag-estimate-card-lbl", text: "Est. Total Tokens" });

    // Candidate Pairs Section
    if (this.params.estimate.candidate_pairs.length > 0) {
      contentEl.createEl("h4", {
        text: `Candidates to Classify (${this.params.estimate.candidate_pairs.length})`,
        cls: "pkmrag-estimate-subhead",
      });

      const list = contentEl.createDiv({ cls: "pkmrag-estimate-pair-list" });
      for (const pair of this.params.estimate.candidate_pairs) {
        const row = list.createDiv({ cls: "pkmrag-estimate-pair-row" });
        const nameSpan = row.createDiv({ cls: "pkmrag-estimate-pair-names" });
        nameSpan.createSpan({ text: displayTitle(pair.source_path, pair.source_title) });
        nameSpan.createSpan({ cls: "pkmrag-estimate-pair-arrow", text: " ↔ " });
        nameSpan.createSpan({ text: displayTitle(pair.target_path, pair.target_title) });

        const pct = Math.round(pair.similarity * 100);
        row.createSpan({ cls: "pkmrag-badge pkmrag-badge-accent", text: `${pct}% similar` });
      }
    } else {
      contentEl.createDiv({
        cls: "pkmrag-empty-state",
        text: "No unlinked pairs found above similarity threshold.",
      });
    }

    // Action Buttons
    const actions = contentEl.createDiv({ cls: "pkmrag-estimate-actions" });

    const cancelBtn = actions.createEl("button", {
      text: "Cancel",
      cls: "pkmrag-btn-sm",
    });
    cancelBtn.onclick = () => this.close();

    const startBtn = actions.createEl("button", {
      text: `Start Discovery (${this.params.estimate.total_tokens.toLocaleString()} tokens)`,
      cls: "pkmrag-btn-sm mod-cta",
    });
    if (this.params.estimate.evaluated_count === 0) {
      startBtn.setAttribute("disabled", "true");
    }

    startBtn.onclick = async () => {
      startBtn.setAttribute("disabled", "true");
      startBtn.setText("Starting...");
      try {
        await this.params.onConfirm();
        this.close();
      } catch (err: unknown) {
        startBtn.removeAttribute("disabled");
        startBtn.setText(`Start Discovery (${this.params.estimate.total_tokens.toLocaleString()} tokens)`);
      }
    };
  }

  onClose(): void {
    this.contentEl.empty();
  }
}
