import { useEffect, useState } from 'react';

interface ImageGenIslandProps {
  prompt: string;
  alt?: string;
  apiUrl?: string;
  cacheKey?: string;
}

export default function ImageGenIsland({
  prompt,
  alt = 'Generated image',
  apiUrl,
  cacheKey,
}: ImageGenIslandProps) {
  const [src, setSrc] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const key = cacheKey || `img-gen-${btoa(prompt).slice(0, 16)}`;

  useEffect(() => {
    // Check localStorage cache first
    const cached = localStorage.getItem(key);
    if (cached) {
      setSrc(cached);
      setLoading(false);
      return;
    }

    // Check if image file already exists in public/generated/
    const publicPath = `/generated/${key}.png`;
    fetch(publicPath)
      .then((res) => {
        if (res.ok) return res.blob();
        throw new Error('Not found');
      })
      .then((blob) => {
        const url = URL.createObjectURL(blob);
        setSrc(url);
        localStorage.setItem(key, url);
        setLoading(false);
      })
      .catch(() => {
        // No cached image, need to generate
        generateImage();
      });
  }, [key, prompt]);

  async function generateImage() {
    setLoading(true);
    setError(null);

    try {
      const url = apiUrl || (typeof window !== 'undefined' ? (window as any).__OH_API_URL__ : undefined) || '/api/generate-image';
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt, key }),
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const data = await res.json();
      const imageUrl = data.url || data.imageUrl || data.data?.[0]?.url;

      if (!imageUrl) throw new Error('No image URL in response');

      // Download and save to public/generated/
      const imgRes = await fetch(imageUrl);
      const imgBlob = await imgRes.blob();
      const blobUrl = URL.createObjectURL(imgBlob);

      setSrc(blobUrl);
      localStorage.setItem(key, blobUrl);
    } catch (e: any) {
      console.error('Image generation error:', e);
      setError(e.message || 'Failed to generate image');
    } finally {
      setLoading(false);
    }
  }

  if (loading) {
    return (
      <div className="animate-pulse bg-gray-200 dark:bg-gray-700 rounded-lg w-full h-64 flex items-center justify-center">
        <span className="text-gray-400 text-sm">Generating image...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="border border-dashed border-gray-300 dark:border-gray-600 rounded-lg p-6 text-center">
        <p className="text-red-500 text-sm mb-3">{error}</p>
        <button
          onClick={generateImage}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700 transition"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="relative group">
      <img src={src!} alt={alt} className="rounded-lg w-full h-auto" />
      <button
        onClick={generateImage}
        className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 px-2 py-1 bg-black/60 text-white text-xs rounded transition"
        title="Regenerate"
      >
        Regenerate
      </button>
    </div>
  );
}
