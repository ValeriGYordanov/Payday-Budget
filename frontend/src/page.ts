import { LitElement } from "lit";
import { ApiError } from "./api";
import { t } from "./i18n";
import type { Settings } from "./types";

/**
 * Base for pages: reloads data whenever `revision` changes (SSE `changed`,
 * or after a write) and reports errors to the app shell.
 */
export abstract class PageElement extends LitElement {
  static override properties = {
    settings: { attribute: false },
    revision: { type: Number },
  };
  declare settings: Settings;
  declare revision: number;

  constructor() {
    super();
    this.revision = 0;
  }

  protected abstract load(): Promise<void>;

  override willUpdate(changed: Map<string, unknown>) {
    if (changed.has("revision")) void this.reload();
  }

  protected async reload() {
    try {
      await this.load();
    } catch (err) {
      this.fail(err);
    }
  }

  /** Report an error to the shell's message bar. */
  protected fail(err: unknown) {
    this.dispatchEvent(
      new CustomEvent("pb-error", { detail: errorMessage(err), bubbles: true, composed: true }),
    );
  }

  /** Tell the shell data changed so every page refreshes now (SSE may lag). */
  protected changed() {
    this.dispatchEvent(new CustomEvent("pb-changed", { bubbles: true, composed: true }));
  }

  /** Run a write; report errors; refresh on success. Returns success. */
  protected async write(action: () => Promise<unknown>): Promise<boolean> {
    try {
      await action();
      this.changed();
      return true;
    } catch (err) {
      this.fail(err);
      return false;
    }
  }
}

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof TypeError) return t("error.offline");
  return t("error.generic");
}
