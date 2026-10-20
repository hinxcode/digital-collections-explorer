const ESCAPED_FORMATTING = /&lt;\/?(b|em|i|strong|sub|sup|u)&gt;/i;

export const hasMarkup = (text) => /[<&]/.test(text);

const parseHtml = (text) => new DOMParser().parseFromString(text, 'text/html').body;

export const parseMarkup = (text) => {
  const body = parseHtml(text);
  return ESCAPED_FORMATTING.test(text) ? parseHtml(body.textContent) : body;
};

export const plainText = (text) => (text && hasMarkup(text) ? parseMarkup(text).textContent : text);
