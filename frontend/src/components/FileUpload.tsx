"use client";

import { useState, useRef, useCallback } from "react";
import { Paperclip, X, FileText, Image as ImageIcon } from "lucide-react";

interface FileUploadProps {
  chatId?: string;
  onFileUploaded?: (document: any) => void;
  onError?: (error: string) => void;
}

interface UploadFile {
  file: File;
  id: string;
  progress: number;
  status: "uploading" | "processing" | "completed" | "error";
  error?: string;
}

export default function FileUpload({ chatId, onFileUploaded, onError }: FileUploadProps) {
  const [files, setFiles] = useState<UploadFile[]>([]);
  const [isDragOver, setIsDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const allowedTypes = [".pdf", ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".txt", ".md"];
  const maxFileSize = 50 * 1024 * 1024; // 50MB

  const validateFile = (file: File): string | null => {
    const ext = "." + file.name.split(".").pop()?.toLowerCase();
    if (!allowedTypes.includes(ext)) {
      return `Unsupported file type. Allowed: ${allowedTypes.join(", ")}`;
    }
    if (file.size > maxFileSize) {
      return "File too large. Maximum 50MB.";
    }
    return null;
  };

  const uploadFile = async (file: File): Promise<void> => {
    const fileId = Math.random().toString(36).substring(7);
    const uploadFile: UploadFile = {
      file,
      id: fileId,
      progress: 0,
      status: "uploading",
    };

    setFiles((prev) => [...prev, uploadFile]);

    try {
      const formData = new FormData();
      formData.append("file", file);
      if (chatId) {
        formData.append("chat_id", chatId);
      }

      const response = await fetch("/api/documents", {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || "Upload failed");
      }

      const result = await response.json();

      setFiles((prev) =>
        prev.map((f) =>
          f.id === fileId
            ? { ...f, progress: 100, status: "processing" }
            : f
        )
      );

      // Simulate processing completion (in real app, would poll or use websocket)
      setTimeout(() => {
        setFiles((prev) =>
          prev.map((f) =>
            f.id === fileId
              ? { ...f, status: "completed" }
              : f
          )
        );
        onFileUploaded?.(result);

        // Remove completed files after a delay
        setTimeout(() => {
          setFiles((prev) => prev.filter((f) => f.id !== fileId));
        }, 3000);
      }, 2000);

    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : "Upload failed";
      setFiles((prev) =>
        prev.map((f) =>
          f.id === fileId
            ? { ...f, status: "error", error: errorMsg }
            : f
        )
      );
      onError?.(errorMsg);
    }
  };

  const handleFiles = useCallback((fileList: FileList) => {
    Array.from(fileList).forEach((file) => {
      const error = validateFile(file);
      if (error) {
        onError?.(error);
        return;
      }
      uploadFile(file);
    });
  }, [onError]);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    handleFiles(e.dataTransfer.files);
  };

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      handleFiles(e.target.files);
    }
    e.target.value = "";
  };

  const removeFile = (id: string) => {
    setFiles((prev) => prev.filter((f) => f.id !== id));
  };

  const getFileIcon = (filename: string) => {
    const ext = filename.split(".").pop()?.toLowerCase();
    if (["png", "jpg", "jpeg", "gif", "bmp", "tiff"].includes(ext || "")) {
      return <ImageIcon size={16} />;
    }
    return <FileText size={16} />;
  };

  const getStatusColor = (status: UploadFile["status"]) => {
    switch (status) {
      case "uploading":
        return "text-blue-400";
      case "processing":
        return "text-yellow-400";
      case "completed":
        return "text-emerald-400";
      case "error":
        return "text-red-400";
    }
  };

  return (
    <div className="relative">
      {/* File Input */}
      <input
        ref={fileInputRef}
        type="file"
        className="hidden"
        accept={allowedTypes.join(",")}
        multiple
        onChange={handleFileInput}
      />

      {/* Upload Button */}
      <button
        onClick={() => fileInputRef.current?.click()}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={`
          p-2 rounded-lg transition-all duration-200
          ${isDragOver
            ? "bg-violet-500/30 text-violet-300"
            : "hover:bg-white/10 text-zinc-400 hover:text-zinc-200"
          }
        `}
        title="Attach file (PDF, images, text)"
      >
        <Paperclip size={20} />
      </button>

      {/* File List */}
      {files.length > 0 && (
        <div className="absolute bottom-full left-0 mb-2 w-72 space-y-2">
          {files.map((file) => (
            <div
              key={file.id}
              className="bg-[#1a1a1e] border border-white/10 rounded-lg p-3 flex items-center gap-3 shadow-xl"
            >
              <div className={`p-2 rounded bg-white/5 ${getStatusColor(file.status)}`}>
                {getFileIcon(file.file.name)}
              </div>

              <div className="flex-1 min-w-0">
                <p className="text-sm text-zinc-200 truncate">{file.file.name}</p>
                <p className="text-xs text-zinc-500">
                  {file.status === "uploading" && "Uploading..."}
                  {file.status === "processing" && "Processing with AI..."}
                  {file.status === "completed" && "Ready!"}
                  {file.status === "error" && file.error || "Error"}
                </p>
              </div>

              <button
                onClick={() => removeFile(file.id)}
                className="p-1 hover:bg-white/10 rounded text-zinc-400 hover:text-zinc-200"
              >
                <X size={16} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
