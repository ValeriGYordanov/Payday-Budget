/** The small part of Home Assistant's frontend API the cards use. */

export interface HassEntity {
  entity_id: string;
  state: string;
  last_updated: string;
}

export interface HassEntityRegistryDisplayEntry {
  entity_id: string;
  platform?: string;
}

export interface HomeAssistant {
  states: Record<string, HassEntity>;
  themes?: { theme?: string; darkMode?: boolean };
  entities?: Record<string, HassEntityRegistryDisplayEntry>;
  connection: {
    sendMessagePromise<T>(message: Record<string, unknown>): Promise<T>;
  };
}

export interface CardConfig {
  type: string;
  title?: string;
  period?: string | number;
  budget?: string | number;
  limit?: number;
  stacked?: boolean;
}

declare global {
  interface Window {
    customCards?: { type: string; name: string; description: string; preview?: boolean }[];
  }
}
