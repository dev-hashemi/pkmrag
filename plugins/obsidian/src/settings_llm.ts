/**
 * AI Discovery and Custom LLM configuration tab section for Orbit Insights.
 */

import { Notice, Setting } from "obsidian";
import type OrbitInsightsPlugin from "./main";

export function renderLlmSection(
  containerEl: HTMLElement,
  plugin: OrbitInsightsPlugin,
  refreshTab: () => void
): void {
  containerEl.createEl("h3", { text: "AI Discovery & Custom LLM Configuration" });

  new Setting(containerEl)
    .setName("LLM Provider")
    .setDesc("Inference provider: Ollama (local offline), OpenAI (cloud), or Custom OpenAI-compatible endpoint")
    .addDropdown((drop) =>
      drop
        .addOption("openai", "OpenAI (Cloud)")
        .addOption("ollama", "Ollama (Local Offline)")
        .addOption("custom", "Custom (Groq, DeepSeek, vLLM, LM Studio)")
        .setValue(plugin.settings.llmProvider)
        .onChange(async (val) => {
          plugin.settings.llmProvider = val as "openai" | "ollama" | "custom";
          if (val === "ollama" && !plugin.settings.llmBaseUrl) {
            plugin.settings.llmBaseUrl = "http://localhost:11434/v1";
            plugin.settings.llmModel = "llama3.2";
          }
          await plugin.saveSettings();
          await syncVaultLlmConfig(plugin);
          refreshTab();
        })
    );

  new Setting(containerEl)
    .setName("Base URL")
    .setDesc("API Base URL (e.g. http://localhost:11434/v1, https://api.openai.com/v1, https://api.groq.com/openai/v1)")
    .addText((text) =>
      text
        .setPlaceholder("https://api.openai.com/v1")
        .setValue(plugin.settings.llmBaseUrl)
        .onChange(async (val) => {
          plugin.settings.llmBaseUrl = val.trim();
          await plugin.saveSettings();
          await syncVaultLlmConfig(plugin);
        })
    );

  new Setting(containerEl)
    .setName("Model Identifier")
    .setDesc("Target model name (e.g. gpt-4o-mini, llama3.2, deepseek-chat, qwen2.5:7b)")
    .addText((text) =>
      text
        .setPlaceholder("gpt-4o-mini")
        .setValue(plugin.settings.llmModel)
        .onChange(async (val) => {
          plugin.settings.llmModel = val.trim();
          await plugin.saveSettings();
          await syncVaultLlmConfig(plugin);
        })
    );

  new Setting(containerEl)
    .setName("API Key")
    .setDesc("Authentication key (optional for local Ollama/LM Studio)")
    .addText((text) => {
      text.inputEl.type = "password";
      text
        .setPlaceholder("sk-...")
        .setValue(plugin.settings.llmApiKey)
        .onChange(async (val) => {
          plugin.settings.llmApiKey = val.trim();
          await plugin.saveSettings();
          await syncVaultLlmConfig(plugin);
        });
    });

  new Setting(containerEl)
    .setName("Test LLM Connection")
    .setDesc("Validate credentials, endpoint connectivity, and structured output response latency")
    .addButton((btn) =>
      btn.setButtonText("Test Connection").onClick(async () => {
        btn.setDisabled(true);
        try {
          const res = await plugin.client.testLlm();
          if (res.success) {
            new Notice(`Success (${res.latency_ms}ms): ${res.message}`);
          } else {
            new Notice(`Test Failed (${res.latency_ms}ms): ${res.message}`);
          }
        } catch (err: unknown) {
          const msg = err instanceof Error ? err.message : String(err);
          new Notice(`LLM Test Failed: ${msg}`);
        } finally {
          btn.setDisabled(false);
        }
      })
    );
}

export async function syncVaultLlmConfig(plugin: OrbitInsightsPlugin): Promise<void> {
  try {
    await plugin.client.saveVaultConfig({
      llm_provider: plugin.settings.llmProvider,
      llm_base_url: plugin.settings.llmBaseUrl,
      llm_model: plugin.settings.llmModel,
      llm_api_key: plugin.settings.llmApiKey,
    });
  } catch {
    // Engine may be stopped; settings remain preserved in Obsidian plugin data
  }
}
