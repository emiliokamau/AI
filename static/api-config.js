// API Configuration
// This file sets up the backend URL for all API calls

(function() {
  // Detect backend URL based on environment
  if (!window.BACKEND_URL) {
    // In production (Vercel), use the Render backend URL
    window.BACKEND_URL = 'https://medic-ai-back-end.onrender.com';
    
    // In development, allow localhost override
    if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
      window.BACKEND_URL = 'http://localhost:5000';
    }
  }

  // Helper function to construct full API URLs
  window.apiUrl = function(path) {
    if (!path.startsWith('/')) {
      path = '/' + path;
    }
    return window.BACKEND_URL + path;
  };

  // Wrapper around fetch to use full URLs
  const originalFetch = window.fetch;
  window.fetch = function(resource, config) {
    // If the resource is a relative path, make it absolute
    if (typeof resource === 'string' && resource.startsWith('/')) {
      resource = window.apiUrl(resource);
    }
    
    // Add CORS credentials by default
    if (typeof config === 'object' && !config.credentials) {
      config.credentials = 'include';
    } else if (!config) {
      config = { credentials: 'include' };
    }
    
    return originalFetch.call(window, resource, config);
  };
})();
