/** Custom element registration that survives Home Assistant's registry polyfill. */

const registered: [string, CustomElementConstructor][] = [];

/** Define a custom element unless the name is taken (the cards share HA's document). */
export function define(name: string, constructor: CustomElementConstructor): void {
  registered.push([name, constructor]);
  if (!customElements.get(name)) customElements.define(name, constructor);
}

/**
 * Define again whatever the current registry does not know. HA's frontend loads
 * extra modules in parallel with its own bundles, which install a scoped
 * custom-element registry polyfill; definitions made before that are invisible to it.
 */
export function defineMissing(): void {
  for (const [name, constructor] of registered) {
    if (customElements.get(name)) continue;
    try {
      customElements.define(name, constructor);
    } catch (err) {
      console.warn(`Payday Budget: could not define ${name}`, err);
    }
  }
}
