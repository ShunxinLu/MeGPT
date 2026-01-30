"use client";

import { useState, useEffect } from "react";
import { ArrowLeft, Upload, Search, Trash2, FileText, Image as ImageIcon, Loader2, Check, AlertCircle } from "lucide-react";
import Link from "next/link";
import FileUpload from "@/components/FileUpload";

interface Document {
    id: string;
    filename: string;
    file_type: string;
    summary: string | null;
    chunk_count: number;
    status: string;
    created_at: string;
}

export default function DocumentsPage() {
    const [documents, setDocuments] = useState<Document[]>([]);
    const [loading, setLoading] = useState(true);
    const [searchQuery, setSearchQuery] = useState("");
    const [selectedDoc, setSelectedDoc] = useState<Document | null>(null);
    const [docContent, setDocContent] = useState<{ content: string; summary: string } | null>(null);
    const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

    useEffect(() => {
        loadDocuments();
    }, []);

    const loadDocuments = async () => {
        try {
            const res = await fetch("/api/documents");
            if (res.ok) {
                const data = await res.json();
                setDocuments(data);
            }
        } catch (error) {
            console.error("Failed to load documents:", error);
        } finally {
            setLoading(false);
        }
    };

    const handleSearch = async () => {
        if (!searchQuery.trim()) {
            loadDocuments();
            return;
        }

        try {
            const res = await fetch(`/api/documents/search?q=${encodeURIComponent(searchQuery)}`);
            if (res.ok) {
                const data = await res.json();
                setDocuments(data.results);
            }
        } catch (error) {
            console.error("Search failed:", error);
        }
    };

    const handleDelete = async (id: string) => {
        if (!confirm("Are you sure you want to delete this document?")) return;

        try {
            const res = await fetch(`/api/documents/${id}`, { method: "DELETE" });
            if (res.ok) {
                setMessage({ type: "success", text: "Document deleted" });
                loadDocuments();
                if (selectedDoc?.id === id) {
                    setSelectedDoc(null);
                    setDocContent(null);
                }
            }
        } catch (error) {
            setMessage({ type: "error", text: "Failed to delete document" });
        }
    };

    const handleViewContent = async (doc: Document) => {
        setSelectedDoc(doc);
        setDocContent(null);

        try {
            const res = await fetch(`/api/documents/${doc.id}/content`);
            if (res.ok) {
                const data = await res.json();
                setDocContent({ content: data.content, summary: data.summary });
            }
        } catch (error) {
            console.error("Failed to load document content:", error);
        }
    };

    const getFileIcon = (type: string) => {
        if (["png", "jpg", "jpeg", "gif", "bmp", "tiff"].includes(type)) {
            return <ImageIcon size={20} />;
        }
        return <FileText size={20} />;
    };

    const getStatusBadge = (status: string) => {
        switch (status) {
            case "completed":
                return <span className="px-2 py-0.5 rounded text-[10px] uppercase font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">Ready</span>;
            case "processing":
                return <span className="px-2 py-0.5 rounded text-[10px] uppercase font-bold bg-yellow-500/20 text-yellow-300 border border-yellow-500/30 flex items-center gap-1"><Loader2 size={10} className="animate-spin" /> Processing</span>;
            case "failed":
                return <span className="px-2 py-0.5 rounded text-[10px] uppercase font-bold bg-red-500/20 text-red-300 border border-red-500/30">Failed</span>;
            default:
                return null;
        }
    };

    return (
        <div className="h-screen overflow-y-auto bg-void text-white relative">
            {/* Background Texture */}
            <div className="fixed inset-0 bg-noise opacity-[0.03] pointer-events-none"></div>

            {/* Header */}
            <div className="sticky top-0 z-10 border-b border-white/5 bg-black/80 backdrop-blur-xl p-4">
                <div className="max-w-6xl mx-auto flex items-center gap-4">
                    <Link
                        href="/"
                        className="p-2 hover:bg-white/10 rounded-lg transition-colors text-zinc-400 hover:text-white"
                    >
                        <ArrowLeft size={20} />
                    </Link>
                    <div className="flex items-center gap-3">
                        <div className="p-2 rounded-lg bg-violet-500/10">
                            <FileText className="text-violet-400" size={20} />
                        </div>
                        <h1 className="text-xl font-bold font-sans tracking-tight">Knowledge Base</h1>
                    </div>
                </div>
            </div>

            {/* Content */}
            <div className="max-w-6xl mx-auto p-6">
                {/* Upload Section */}
                <section className="mb-8 bg-white/[0.03] border border-white/5 rounded-2xl p-6">
                    <div className="flex items-center justify-between mb-4">
                        <h2 className="text-lg font-semibold text-zinc-200">Upload Documents</h2>
                        <FileUpload onError={(error) => setMessage({ type: "error", text: error })} />
                    </div>
                    <p className="text-sm text-zinc-500">
                        Supports PDF, images (PNG, JPG), and text files. Documents are processed with AI for OCR and content extraction.
                    </p>
                </section>

                {/* Search */}
                <section className="mb-6">
                    <div className="relative">
                        <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-zinc-500" size={20} />
                        <input
                            type="text"
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
                            placeholder="Search documents..."
                            className="w-full pl-12 pr-4 py-3 bg-white/[0.03] border border-white/10 rounded-xl text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-violet-500/50 transition-colors"
                        />
                    </div>
                </section>

                {/* Message */}
                {message && (
                    <div className={`mb-6 p-4 rounded-xl flex items-center gap-3 border ${message.type === "success"
                        ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400"
                        : "bg-red-500/10 border-red-500/20 text-red-400"
                    }`}>
                        {message.type === "success" ? <Check size={18} /> : <AlertCircle size={18} />}
                        <span className="font-medium text-sm">{message.text}</span>
                    </div>
                )}

                {/* Documents Grid */}
                {loading ? (
                    <div className="flex items-center justify-center py-20">
                        <Loader2 className="animate-spin text-violet-400" size={32} />
                    </div>
                ) : documents.length === 0 ? (
                    <div className="text-center py-20">
                        <div className="w-16 h-16 rounded-2xl bg-white/5 flex items-center justify-center mx-auto mb-4">
                            <FileText className="text-zinc-600" size={32} />
                        </div>
                        <h3 className="text-lg font-medium text-zinc-400 mb-2">No documents yet</h3>
                        <p className="text-sm text-zinc-600">Upload a document to get started</p>
                    </div>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                        {documents.map((doc) => (
                            <div
                                key={doc.id}
                                className="bg-white/[0.03] border border-white/5 rounded-xl p-4 hover:border-violet-500/30 transition-all cursor-pointer group"
                                onClick={() => handleViewContent(doc)}
                            >
                                <div className="flex items-start justify-between mb-3">
                                    <div className="p-2 rounded-lg bg-white/5 text-zinc-400 group-hover:text-violet-400 transition-colors">
                                        {getFileIcon(doc.file_type)}
                                    </div>
                                    {getStatusBadge(doc.status)}
                                </div>
                                <h3 className="font-medium text-zinc-200 truncate mb-1">{doc.filename}</h3>
                                <p className="text-xs text-zinc-500 mb-3">
                                    {new Date(doc.created_at).toLocaleDateString()}
                                </p>
                                {doc.summary && (
                                    <p className="text-sm text-zinc-400 line-clamp-2">
                                        {doc.summary.slice(0, 150)}...
                                    </p>
                                )}
                                <button
                                    onClick={(e) => {
                                        e.stopPropagation();
                                        handleDelete(doc.id);
                                    }}
                                    className="mt-3 text-xs text-red-400 hover:text-red-300 opacity-0 group-hover:opacity-100 transition-opacity"
                                >
                                    Delete
                                </button>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            {/* Document Detail Modal */}
            {selectedDoc && (
                <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-[#1a1a1e] border border-white/10 rounded-2xl w-full max-w-4xl max-h-[80vh] overflow-hidden flex flex-col">
                        <div className="p-4 border-b border-white/5 flex items-center justify-between">
                            <h2 className="text-lg font-semibold text-zinc-200">{selectedDoc.filename}</h2>
                            <button
                                onClick={() => setSelectedDoc(null)}
                                className="p-2 hover:bg-white/10 rounded-lg text-zinc-400 hover:text-white"
                            >
                                ✕
                            </button>
                        </div>
                        <div className="p-6 overflow-y-auto flex-1">
                            {docContent ? (
                                <div className="prose prose-invert max-w-none">
                                    <h3 className="text-sm font-medium text-zinc-500 mb-2">Summary</h3>
                                    <p className="text-zinc-300 mb-6">{docContent.summary || "No summary available"}</p>
                                    <h3 className="text-sm font-medium text-zinc-500 mb-2">Content</h3>
                                    <pre className="whitespace-pre-wrap text-sm text-zinc-300 bg-black/30 p-4 rounded-lg border border-white/5 overflow-x-auto">
                                        {docContent.content.slice(0, 10000)}
                                        {docContent.content.length > 10000 && "\n\n... (content truncated)"}
                                    </pre>
                                </div>
                            ) : (
                                <div className="flex items-center justify-center py-20">
                                    <Loader2 className="animate-spin text-violet-400" size={32} />
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
