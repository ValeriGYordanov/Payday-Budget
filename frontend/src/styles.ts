import { css } from "lit";

/** Shared component styles. Colour tokens are defined on :root in index.html. */
export const shared = css`
  :host {
    color: var(--pb-text);
    font: inherit;
  }
  * {
    box-sizing: border-box;
  }
  h2 {
    font-size: 1.1rem;
    margin: 0 0 12px;
  }
  .card {
    background: var(--pb-surface);
    border: 1px solid var(--pb-border);
    border-radius: 12px;
    padding: 16px;
    margin-bottom: 16px;
  }
  .row {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .spacer {
    flex: 1;
  }
  .muted {
    color: var(--pb-text-muted);
    font-size: 0.875rem;
  }
  .error {
    color: var(--pb-negative);
    font-size: 0.875rem;
  }
  .positive {
    color: var(--pb-positive);
  }
  .negative {
    color: var(--pb-negative);
  }
  .amount {
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }
  button {
    font: inherit;
    border-radius: 8px;
    border: 1px solid var(--pb-border);
    background: var(--pb-surface);
    color: var(--pb-text);
    padding: 8px 14px;
    min-height: 40px;
    cursor: pointer;
  }
  button.primary {
    background: var(--pb-primary);
    border-color: var(--pb-primary);
    color: var(--pb-on-primary);
  }
  button.danger {
    color: var(--pb-negative);
  }
  button.icon {
    padding: 8px;
    min-width: 40px;
    border: none;
    background: transparent;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }
  button:disabled {
    opacity: 0.5;
    cursor: default;
  }
  label.field {
    display: flex;
    flex-direction: column;
    gap: 4px;
    margin-bottom: 12px;
    font-size: 0.875rem;
    color: var(--pb-text-muted);
  }
  input,
  select,
  textarea {
    font: inherit;
    font-size: 1rem;
    color: var(--pb-text);
    background: var(--pb-input);
    border: 1px solid var(--pb-border);
    border-radius: 8px;
    padding: 8px 10px;
    min-height: 40px;
    width: 100%;
  }
  input[type="checkbox"] {
    width: auto;
    min-height: auto;
  }
  .segmented {
    display: flex;
    border: 1px solid var(--pb-border);
    border-radius: 8px;
    overflow: hidden;
  }
  .segmented button {
    flex: 1;
    border: none;
    border-radius: 0;
  }
  .segmented button[aria-pressed="true"] {
    background: var(--pb-primary);
    color: var(--pb-on-primary);
  }
  ul.list {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  ul.list > li {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 0;
    border-bottom: 1px solid var(--pb-border);
    min-height: 48px;
  }
  ul.list > li:last-child {
    border-bottom: none;
  }
  .grow {
    flex: 1;
    min-width: 0;
  }
  .ellipsis {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .badge {
    font-size: 0.75rem;
    border: 1px solid var(--pb-border);
    border-radius: 999px;
    padding: 1px 8px;
    color: var(--pb-text-muted);
  }
  .actions {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
    flex-wrap: wrap;
    margin-top: 8px;
  }
`;
