import axios from 'axios';

const API_BASE_URL = 'http://localhost:8000';

/**
 * Sends the CV file and job description to the backend API for analysis.
 * 
 * @param {File} file - The PDF file of the CV.
 * @param {string} [jobDescription=""] - Optional job description for tailoring.
 * @returns {Promise<Object>} The analysis result from the AI.
 * @throws {Error} If the API request fails or returns an error.
 */
export const analyzeCV = async (file, jobDescription) => {
  const formData = new FormData();
  if (file) {
    formData.append('cv_file', file);
  }
  
  if (jobDescription) {
    formData.append('job_description', jobDescription);
  }

  try {
    const response = await axios.post(`${API_BASE_URL}/analyze`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  } catch (error) {
    console.error('Error analyzing CV:', error);
    if (error.response && error.response.data && error.response.data.detail) {
      throw new Error(error.response.data.detail);
    }
    throw new Error('Failed to connect to the server or analyze the CV.');
  }
};

/**
 * Fetches the user's Master Profile from the backend.
 * 
 * @returns {Promise<Object>} The master profile data.
 * @throws {Error} If the API request fails.
 */
export const getProfile = async () => {
  try {
    const response = await axios.get(`${API_BASE_URL}/profile`);
    return response.data;
  } catch (error) {
    console.error('Error fetching profile:', error);
    // Surface the backend's reason (e.g. a corrupt master_profile.json) instead of a generic message.
    throw new Error(error.response?.data?.detail || 'Failed to fetch Master Profile.');
  }
};

/**
 * Updates the user's Master Profile in the backend.
 * 
 * @param {Object} profile - The master profile data to save.
 * @returns {Promise<Object>} Success message from the backend.
 * @throws {Error} If the API request fails.
 */
export const updateProfile = async (profile) => {
  try {
    const response = await axios.post(`${API_BASE_URL}/profile`, profile, {
      headers: {
        'Content-Type': 'application/json',
      },
    });
    return response.data;
  } catch (error) {
    console.error('Error updating profile:', error);
    throw new Error('Failed to update Master Profile.');
  }
};

/**
 * Extracts profile data from a CV (PDF) using the backend AI service.
 * 
 * @param {File} file - The PDF file to extract from.
 * @returns {Promise<Object>} The extracted master profile data.
 * @throws {Error} If the API request fails.
 */
export const extractProfileFromCV = async (file) => {
  const formData = new FormData();
  formData.append('cv_file', file);

  try {
    const response = await axios.post(`${API_BASE_URL}/profile/extract`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  } catch (error) {
    console.error('Error extracting profile:', error);
    if (error.response && error.response.data && error.response.data.detail) {
      throw new Error(error.response.data.detail);
    }
    throw new Error('Failed to extract profile from CV.');
  }
};

/**
 * Generates an ATS CV Preview (JSON) from the Master Profile based on a job description.
 * 
 * @param {string} jobDescription - The job description text to tailor the CV.
 * @param {string} language - The target language for the CV (e.g. 'English', 'Indonesian').
 * @returns {Promise<Object>} The structured CV data.
 * @throws {Error} If the API request fails.
 */
export const generatePreview = async (jobDescription, language = 'English') => {
  const formData = new FormData();
  if (jobDescription) {
    formData.append('job_description', jobDescription);
  }
  if (language) {
    formData.append('language', language);
  }

  try {
    const response = await axios.post(`${API_BASE_URL}/generate/preview`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  } catch (error) {
    console.error('Error generating CV preview:', error);
    if (error.response && error.response.data && error.response.data.detail) {
      throw new Error(error.response.data.detail);
    }
    throw new Error('Failed to generate CV preview.');
  }
};

/**
 * POSTs JSON to a backend endpoint that returns a file, and saves it in the browser.
 * Uses the filename from the Content-Disposition header when present.
 *
 * @param {string} path - Endpoint path, e.g. '/generate/pdf/from-json'.
 * @param {Object} body - JSON body to send.
 * @param {string} defaultName - Filename used when the server sends none.
 * @throws {Error} With the backend's `detail` message when available.
 */
const downloadFile = async (path, body, defaultName) => {
  let response;
  try {
    response = await axios.post(`${API_BASE_URL}${path}`, body, { responseType: 'blob' });
  } catch (error) {
    console.error(`Error downloading ${defaultName}:`, error);
    // Error bodies arrive as a Blob because of responseType: 'blob'; read the JSON inside.
    let detail = null;
    if (error.response?.data instanceof Blob) {
      try {
        detail = JSON.parse(await error.response.data.text()).detail;
      } catch {
        // Not JSON; fall through to the generic message.
      }
    }
    throw new Error(detail || `Failed to download ${defaultName}.`);
  }

  const match = response.headers['content-disposition']?.match(/filename="?([^"]+)"?/);
  const url = window.URL.createObjectURL(response.data);
  const link = document.createElement('a');
  link.href = url;
  link.setAttribute('download', match ? match[1] : defaultName);
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
};

/**
 * Generates an ATS CV (DOCX format) from a StructuredCV JSON object and downloads it.
 *
 * @param {Object} structuredCV - The structured CV data.
 * @throws {Error} If the API request fails.
 */
export const downloadCVFromJson = (structuredCV) =>
  downloadFile('/generate/docx/from-json', structuredCV, 'Tailored_CV.docx');

/**
 * Generates an ATS CV (PDF format) from a StructuredCV JSON object and downloads it.
 *
 * @param {Object} structuredCV - The structured CV data.
 * @throws {Error} If the API request fails.
 */
export const downloadCVPdfFromJson = (structuredCV) =>
  downloadFile('/generate/pdf/from-json', structuredCV, 'Tailored_CV.pdf');

/**
 * Applies a single analysis suggestion to generate an improved CV.
 * Calls POST /apply-suggestion with the suggestion text and context.
 *
 * @param {string} suggestion - The suggestion text to apply.
 * @param {string} [jobDescription=""] - Optional job description for context.
 * @param {Object|null} [originalCV=null] - Optional current StructuredCV before fix.
 * @param {string} [language="English"] - Target language for the CV output.
 * @returns {Promise<Object>} The improved StructuredCV data.
 * @throws {Error} If the API request fails or rate limit is exceeded.
 */
export const applySuggestion = async (suggestion, jobDescription = '', originalCV = null, language = 'English') => {
  const formData = new FormData();
  formData.append('suggestion', suggestion);

  if (jobDescription) {
    formData.append('job_description', jobDescription);
  }

  if (originalCV) {
    formData.append('original_cv', JSON.stringify(originalCV));
  }

  if (language) {
    formData.append('language', language);
  }

  try {
    const response = await axios.post(`${API_BASE_URL}/apply-suggestion`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  } catch (error) {
    console.error('Error applying suggestion:', error);
    if (error.response && error.response.data && error.response.data.detail) {
      throw new Error(error.response.data.detail);
    }
    throw new Error('Failed to apply suggestion.');
  }
};
