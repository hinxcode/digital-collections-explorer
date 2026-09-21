const API_URL = import.meta.env.API_BASE_URL;

const VISITOR_FACING_STATUSES = [400, 411, 413, 429, 503];

const failure = async (response) => {
  const error = new Error(`API error: ${response.status}`);
  if (VISITOR_FACING_STATUSES.includes(response.status)) {
    const body = await response.json().catch(() => null);
    if (body && typeof body.detail === 'string') {
      error.visitorMessage = body.detail;
    }
  }
  return error;
};

/**
 * Search for similar photographs by text
 * @param {string} query - The text query
 * @param {number} limit - Maximum number of results to return (default: 50)
 * @param {number} page - Page number for pagination (default: 1)
 * @returns {Promise<Array>} - Array of search results
 */
export const searchByText = async (query, limit = 50, page = 1) => {
  try {
    const pageParam = Math.max(1, parseInt(page) || 1);
    const response = await fetch(`${API_URL}/api/search/text?query=${encodeURIComponent(query)}&limit=${limit}&page=${pageParam}`);
    
    if (!response.ok) {
      throw await failure(response);
    }
    
    const { results } = await response.json();
    return results;
  } catch (error) {
    console.error('Error searching photos:', error);
    throw error;
  }
};

/**
 * Search for similar photographs by image
 * @param {File} image - The image file to search with
 * @param {number} limit - Maximum number of results to return
 * @param {number} page - Page number for pagination
 * @returns {Promise<Array>} - Array of search results
 */
export const searchByImage = async (image, limit = 50, page = 1) => {
  try {
    const formData = new FormData();
    formData.append('image', image);
    formData.append('limit', limit);
    formData.append('page', page);

    const response = await fetch(`${API_URL}/api/search/image`, {
      method: 'POST',
      body: formData,
    });
    
    if (!response.ok) {
      throw await failure(response);
    }
    
    const { results } = await response.json();
    return results;
  } catch (error) {
    console.error('Error in image search:', error);
    throw error;
  }
};

/**
 * Get statistics about embeddings (total count)
 * @returns {Promise<Object>} - Statistics object with count property
 */
export const getEmbeddingStats = async () => {
  try {
    const response = await fetch(`${API_URL}/api/embeddings/count`);
    
    if (!response.ok) {
      throw new Error(`API error: ${response.status}`);
    }
    
    const data = await response.json();
    return data;
  } catch (error) {
    console.error('Error fetching embedding stats:', error);
    throw error;
  }
};

const getJson = async (path) => {
  const response = await fetch(`${API_URL}${path}`);

  if (!response.ok) {
    throw new Error(`API error: ${response.status}`);
  }

  return response.json();
};

/**
 * Describe the collection: title, size, suggested searches, licence and links
 * @returns {Promise<Object>}
 */
export const getCollection = () => getJson('/api/collection');

/**
 * Get a varied handful of images to start wandering from, one per object
 * @param {number} limit - How many images
 * @param {number} seed - The same seed always gives the same order
 * @param {number} offset - Continue the same order further on, without repeats
 * @returns {Promise<{results: Array, has_more: boolean}>}
 */
export const getSample = (limit, seed, offset = 0) => (
  getJson(`/api/items/sample?limit=${limit}&seed=${seed}&offset=${offset}`)
);

/**
 * Get one image, with the other images of the same object
 * @param {string} id - The item ID
 * @returns {Promise<Object>}
 */
export const getItem = (id) => getJson(`/api/items/${encodeURIComponent(id)}`);

/**
 * Get images of other objects that look most like this one
 * @param {string} id - The item ID
 * @param {number} limit - How many images
 * @returns {Promise<Array>}
 */
export const getSimilar = async (id, limit = 24) => {
  const { results } = await getJson(`/api/items/${encodeURIComponent(id)}/similar?limit=${limit}`);
  return results;
};
