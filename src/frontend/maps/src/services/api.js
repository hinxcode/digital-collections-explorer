const sitePath = () => window.location.pathname.replace(/\/index\.html$/, '').replace(/\/$/, '');
const API_URL = import.meta.env.API_BASE_URL || sitePath();

export const getIiifInfo = async (iiifId) => {
  const url = `https://tile.loc.gov/image-services/iiif/${iiifId}/info.json`;

  try {
    const response = await fetch(url);
    
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    return await response.json();
  } catch (error) {
    console.error(`Failed to fetch IIIF info for ${iiifId}:`, error);
    throw error;
  }
};

export const getLocInfo = async (locItemUrl) => {
  try {
    const urlObject = new URL(locItemUrl);
    urlObject.protocol = 'https';
    urlObject.searchParams.set('fo', 'json');

    const response = await fetch(urlObject.href);
    
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    return await response.json();
  } catch (error) {
    console.error(`Failed to process or fetch LOC info for ${locItemUrl}:`, error);
    throw error;
  }
};

/**
 * Search for maps by text query
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
      throw new Error(`API error: ${response.status}`);
    }
    
    const { results } = await response.json();
    
    return results.map(item => ({
      id: item.id,
      file_path: item.file_path,
      similarity: item.score,
      metadata: item.metadata
    }));
  } catch (error) {
    console.error('Error searching photos:', error);
    throw error;
  }
};

/**
 * Search for similar maps by image
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
      throw new Error(`API error: ${response.status}`);
    }
    
    const { results } = await response.json();

    return results.map(item => ({
      id: item.id,
      file_path: item.file_path,
      similarity: item.score,
      metadata: item.metadata
    }));
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
