const sitePath = () => window.location.pathname.replace(/\/index\.html$/, '').replace(/\/$/, '');
const API_URL = import.meta.env.API_BASE_URL || sitePath();

export const searchContent = async (query, limit = 30, page = 1) => {
  try {
    const response = await fetch(
      `${API_URL}/api/search/text?query=${encodeURIComponent(query)}&limit=${limit}&page=${page}`
    );
    
    if (!response.ok) {
      throw new Error(`API error: ${response.status}`);
    }
    
    const { results } = await response.json();
    
    const transformedResults = results.map(item => {
      const result = {
        id: item.id,
        file_name: item.metadata.file_name || item.id.split('_')[0],
        original_file: item.metadata.paths?.original || '',
        thumbnail_path: item.metadata.paths?.thumbnail || '',
        processed_path: item.metadata.paths?.processed || '',
        score: item.score || 0,
        type: item.metadata.type,
        page: item.metadata.page,
        n_pages: item.metadata.n_pages
      };
      
      return result;
    });
    
    return transformedResults;
  } catch (error) {
    console.error('Error searching content:', error);
    throw error;
  }
};

export const searchByImage = async (imageFile, resultsPerPage = 30, page = 1) => {
  try {
    const formData = new FormData();

    formData.append('image', imageFile);
    formData.append('resultsPerPage', resultsPerPage);
    formData.append('page', page);
    
    const response = await fetch(`${API_URL}/api/search/image`, {
      method: 'POST',
      body: formData
    });
    
    if (!response.ok) {
      throw new Error(`API error: ${response.status}`);
    }
    
    const { results } = await response.json();
    
    return results;
  } catch (error) {
    console.error('Error searching by image:', error);
    throw error;
  }
};

export const getImageUrl = (documentId, size) => {
  if (!documentId) return '';

  if (size) {
    return `${API_URL}/images/${encodeURIComponent(documentId)}?size=${size}`;
  }
  
  return `${API_URL}/images/${encodeURIComponent(documentId)}`;
};

export const getDownloadUrl = (documentId) => {
  if (!documentId) return '';
  
  return `${API_URL}/static/${encodeURIComponent(documentId)}`;
};
