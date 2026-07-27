const API_URL = import.meta.env.API_BASE_URL;

// Normalize a raw API result (free-form metadata dict) into a flat media item.
const toMediaItem = (item) => ({
  id: item.id,
  file_name: item.metadata?.file_name || item.id.split('_')[0],
  type: item.metadata?.type || 'unknown',
  original_file: item.metadata?.paths?.original || '',
  thumbnail_path: item.metadata?.paths?.thumbnail || '',
  processed_path: item.metadata?.paths?.processed || '',
  score: item.score || 0,
});

export const searchByText = async (query, limit = 30, page = 1) => {
  const response = await fetch(
    `${API_URL}/api/search/text?query=${encodeURIComponent(query)}&limit=${limit}&page=${page}`
  );

  if (!response.ok) {
    throw new Error(`API error: ${response.status}`);
  }

  const { results } = await response.json();
  return results.map(toMediaItem);
};

export const searchByImage = async (imageFile, limit = 30, page = 1) => {
  const formData = new FormData();
  formData.append('image', imageFile);
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
  return results.map(toMediaItem);
};

// Visual card image (video poster frame / audio waveform).
export const getImageUrl = (id, size) => {
  if (!id) return '';
  return size
    ? `${API_URL}/images/${encodeURIComponent(id)}?size=${size}`
    : `${API_URL}/images/${encodeURIComponent(id)}`;
};

// Inline, range-enabled stream for <audio>/<video> playback.
export const getMediaUrl = (id) => {
  if (!id) return '';
  return `${API_URL}/media/${encodeURIComponent(id)}`;
};

// Attachment download of the original file.
export const getDownloadUrl = (id) => {
  if (!id) return '';
  return `${API_URL}/static/${encodeURIComponent(id)}`;
};

export const getEmbeddingStats = async () => {
  try {
    const response = await fetch(`${API_URL}/api/embeddings/count`);
    if (!response.ok) {
      throw new Error(`API error: ${response.status}`);
    }
    return await response.json();
  } catch (error) {
    console.error('Error fetching embedding stats:', error);
    return { count: 0 };
  }
};
