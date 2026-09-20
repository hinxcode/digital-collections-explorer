/**
 * The title to show for an item, or null when it has no catalog record
 * @param {Object} item - An item as returned by the API
 * @returns {string|null}
 */
export const titleOf = (item) => item.metadata?.title || null;
