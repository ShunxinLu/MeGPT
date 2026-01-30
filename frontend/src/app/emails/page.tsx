"use client";

import { useState } from "react";
import {
  Mail,
  Search,
  Archive,
  Trash2,
  CheckCircle,
  Clock,
  AlertCircle,
  X,
  RefreshCw,
  Filter,
  MoreVertical,
} from "lucide-react";

/**
 * Email Management Interface
 * Modern glassmorphism design with classification badges and search
 * Uses bento grid layout for efficient organization
 */
type Email = {
  id: string;
  threadId: string;
  subject: string;
  sender: string;
  senderEmail: string;
  body: string;
  date: string;
  priority: "critical" | "important" | "normal" | "low" | "spam";
  category: string;
  isRead: boolean;
  isSpam: boolean;
  hasAttachments: boolean;
  summary: string;
  actionItems: string[];
};

type ViewMode = "list" | "detail" | "thread";

const MOCK_EMAILS: Email[] = [
  {
    id: "1",
    threadId: "thread-1",
    subject: "Family Reunion Planning - Final Details",
    sender: "Sarah Johnson",
    senderEmail: "sarah.johnson@email.com",
    body: "Hi everyone, just wanted to confirm the final details for our family reunion next month...",
    date: "2025-01-19T09:30:00Z",
    priority: "important",
    category: "personal",
    isRead: false,
    isSpam: false,
    hasAttachments: true,
    summary: "Discussion about finalizing family reunion logistics, including venue confirmation and catering options.",
    actionItems: [
      "Confirm final headcount by Friday",
      "Submit dietary restrictions",
      "Coordinate travel arrangements",
    ],
  },
  {
    id: "2",
    threadId: "thread-2",
    subject: "Q4 Financial Review - Action Required",
    sender: "Investment Advisor",
    senderEmail: "advisor@financial.com",
    body: "Dear valued client, please review your Q4 portfolio performance and consider the following recommendations...",
    date: "2025-01-19T08:15:00Z",
    priority: "critical",
    category: "finance",
    isRead: false,
    isSpam: false,
    hasAttachments: true,
    summary: "Quarterly financial review with portfolio performance analysis and investment recommendations.",
    actionItems: [
      "Review portfolio performance",
      "Review investment recommendations",
      "Confirm asset allocation strategy",
    ],
  },
  {
    id: "3",
    threadId: "thread-3",
    subject: "Calendar Event Proposal: Team Meeting",
    sender: "Work Calendar Bot",
    senderEmail: "calendar@company.com",
    body: "A new calendar event has been proposed for your approval...",
    date: "2025-01-19T07:45:00Z",
    priority: "important",
    category: "work",
    isRead: false,
    isSpam: false,
    hasAttachments: false,
    summary: "Calendar proposal for team meeting on January 25th at 2:00 PM.",
    actionItems: [
      "Approve or reject calendar proposal",
      "Review meeting agenda",
    ],
  },
];

export default function EmailsPage() {
  const [emails, setEmails] = useState<Email[]>(MOCK_EMAILS);
  const [selectedEmail, setSelectedEmail] = useState<Email | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>("list");
  const [searchQuery, setSearchQuery] = useState("");
  const [filterPriority, setFilterPriority] = useState<string>("all");
  const [filterCategory, setFilterCategory] = useState<string>("all");
  const [loading, setLoading] = useState(false);

  // Filter emails based on search and filters
  const filteredEmails = emails.filter((email) => {
    const matchesSearch =
      searchQuery === "" ||
      email.subject.toLowerCase().includes(searchQuery.toLowerCase()) ||
      email.sender.toLowerCase().includes(searchQuery.toLowerCase()) ||
      email.body.toLowerCase().includes(searchQuery.toLowerCase());

    const matchesPriority =
      filterPriority === "all" || email.priority === filterPriority;

    const matchesCategory =
      filterCategory === "all" || email.category === filterCategory;

    return matchesSearch && matchesPriority && matchesCategory;
  });

  const handleEmailClick = (email: Email) => {
    setSelectedEmail(email);
    setViewMode("detail");
  };

  const handleMarkRead = (emailId: string) => {
    setEmails((prev) =>
      prev.map((e) =>
        e.id === emailId ? { ...e, isRead: true } : e
      )
    );
  };

  const handleArchive = (emailId: string) => {
    // Archive logic
    console.log("Archive email:", emailId);
  };

  const handleDelete = (emailId: string) => {
    setEmails((prev) => prev.filter((e) => e.id !== emailId));
    if (selectedEmail?.id === emailId) {
      setSelectedEmail(null);
      setViewMode("list");
    }
  };

  const handleRefresh = () => {
    setLoading(true);
    setTimeout(() => setLoading(false), 1000);
  };

  const getPriorityColor = (priority: string) => {
    switch (priority) {
      case "critical":
        return "text-white bg-red-500 border-red-500";
      case "important":
        return "text-white bg-orange-500 border-orange-500";
      case "normal":
        return "text-white bg-blue-500 border-blue-500";
      case "low":
        return "text-white bg-gray-500 border-gray-500";
      case "spam":
        return "text-white bg-purple-500 border-purple-500";
      default:
        return "text-white bg-gray-500 border-gray-500";
    }
  };

  const getPriorityIcon = (priority: string) => {
    switch (priority) {
      case "critical":
        return <AlertCircle className="w-3 h-3" />;
      case "important":
        return <Clock className="w-3 h-3" />;
      case "normal":
        return <Mail className="w-3 h-3" />;
      case "low":
        return <Clock className="w-3 h-3" />;
      case "spam":
        return <AlertCircle className="w-3 h-3" />;
      default:
        return <Mail className="w-3 h-3" />;
    }
  };

  const formatDate = (date: string) => {
    const dateObj = new Date(date);
    const now = new Date();
    const diffInHours = Math.floor(
      (now.getTime() - dateObj.getTime()) / (1000 * 60 * 60)
    );

    if (diffInHours < 1) return "Just now";
    if (diffInHours < 24) return `${diffInHours}h ago`;
    if (diffInHours < 48) return "Yesterday";
    return dateObj.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
    });
  };

  // Email List View
  if (viewMode === "list") {
    return (
      <div className="flex flex-col h-screen pt-20 bg-void">
        {/* Header with Search */}
        <div className="bg-white/95 backdrop-blur-md border-b border-gray-200 px-6 py-4">
          <div className="max-w-7xl mx-auto">
            <div className="flex items-center justify-between">
              {/* Search Bar */}
              <div className="flex-1 max-w-2xl">
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-tertiary" />
                  <input
                    type="text"
                    placeholder="Search emails..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-full pl-12 pr-4 py-3 rounded-lg bg-white/80 border border-gray-200 focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all duration-200"
                  />
                </div>
              </div>

              {/* Actions */}
              <div className="flex items-center space-x-3 ml-6">
                {/* Priority Filter */}
                <select
                  value={filterPriority}
                  onChange={(e) => setFilterPriority(e.target.value)}
                  className="px-4 py-2 rounded-lg bg-white/80 border border-gray-200 focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all duration-200 cursor-pointer"
                >
                  <option value="all">All Priorities</option>
                  <option value="critical">Critical</option>
                  <option value="important">Important</option>
                  <option value="normal">Normal</option>
                  <option value="low">Low</option>
                  <option value="spam">Spam</option>
                </select>

                {/* Refresh Button */}
                <button
                  onClick={handleRefresh}
                  disabled={loading}
                  className="p-2 rounded-lg bg-primary/10 hover:bg-primary/20 border border-primary/20 transition-all duration-200 cursor-pointer"
                >
                  <RefreshCw
                    className={`w-5 h-5 text-primary ${
                      loading ? "animate-spin" : ""
                    }`}
                  />
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Email List */}
        <div className="flex-1 overflow-auto">
          <div className="max-w-7xl mx-auto px-6 py-6">
            <div className="grid grid-cols-1 gap-4">
              {filteredEmails.map((email) => (
                <div
                  key={email.id}
                  onClick={() => handleEmailClick(email)}
                  className={`glass-card rounded-2xl p-6 cursor-pointer transition-all duration-200 hover:scale-[1.01] hover:shadow-lg ${
                    !email.isRead ? "border-l-4 border-l-accent-primary" : ""
                  }`}
                >
                  {/* Header */}
                  <div className="flex items-start justify-between mb-4">
                    <div className="flex items-center space-x-3">
                      {/* Sender Avatar */}
                      <div className="w-12 h-12 rounded-full bg-gradient-to-br from-violet-500/30 to-fuchsia-500/30 flex items-center justify-center">
                        <span className="text-lg font-bold text-white">
                          {email.sender.charAt(0).toUpperCase()}
                        </span>
                      </div>

                      {/* Sender Name & Email */}
                      <div>
                        <div className="font-medium text-primary">
                          {email.sender}
                        </div>
                        <div className="text-sm text-tertiary">
                          {email.senderEmail}
                        </div>
                      </div>
                    </div>

                    {/* Date & Actions */}
                    <div className="flex items-center space-x-3">
                      <span className="text-sm text-tertiary">
                        {formatDate(email.date)}
                      </span>

                      {/* Quick Actions */}
                      <div className="flex items-center space-x-2">
                        {!email.isRead && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handleMarkRead(email.id);
                            }}
                            className="p-2 rounded-lg bg-primary/10 hover:bg-primary/20 border border-primary/20 transition-all duration-200 cursor-pointer"
                          >
                            <CheckCircle className="w-4 h-4 text-primary" />
                          </button>
                        )}
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleArchive(email.id);
                          }}
                          className="p-2 rounded-lg bg-success/10 hover:bg-success/20 border border-success/20 transition-all duration-200 cursor-pointer"
                        >
                          <Archive className="w-4 h-4 text-success" />
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDelete(email.id);
                          }}
                          className="p-2 rounded-lg bg-error/10 hover:bg-error/20 border border-error/20 transition-all duration-200 cursor-pointer"
                        >
                          <Trash2 className="w-4 h-4 text-error" />
                        </button>
                      </div>
                    </div>
                  </div>

                  {/* Subject & Priority Badge */}
                  <div className="flex items-start space-x-3 mb-4">
                    <div className="flex-1">
                      <div className="flex items-center space-x-2">
                        <h3 className="font-semibold text-primary text-lg">
                          {email.subject}
                        </h3>
                        <span
                          className={`px-2 py-1 rounded-md text-xs font-medium flex items-center space-x-1 ${getPriorityColor(
                            email.priority
                          )}`}
                        >
                          {getPriorityIcon(email.priority)}
                          <span className="uppercase">{email.priority}</span>
                        </span>
                      </div>
                    </div>

                    {/* Category Badge */}
                    <span className="px-2 py-1 rounded-md bg-accent-cyan/10 text-accent-cyan text-xs font-medium border border-accent-cyan/20">
                      {email.category}
                    </span>
                  </div>

                  {/* Summary */}
                  {email.summary && (
                    <p className="text-secondary mb-4">
                      {email.summary}
                    </p>
                  )}

                  {/* Action Items */}
                  {email.actionItems && email.actionItems.length > 0 && (
                    <div className="border-t border-gray-200 pt-3">
                      <div className="text-sm font-medium text-tertiary mb-2">
                        Action Items:
                      </div>
                      <ul className="space-y-2">
                        {email.actionItems.map((item, idx) => (
                          <li
                            key={idx}
                            className="flex items-start space-x-2 text-sm text-secondary"
                          >
                            <span className="mt-1 text-accent-tertiary">
                              •
                            </span>
                            <span>{item}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              ))}
            </div>

            {filteredEmails.length === 0 && (
              <div className="flex flex-col items-center justify-center py-16">
                <Mail className="w-16 h-16 text-tertiary mb-4" />
                <h3 className="font-semibold text-primary text-lg mb-2">
                  No emails found
                </h3>
                <p className="text-secondary">
                  Try adjusting your search or filters
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  // Email Detail View
  if (viewMode === "detail" && selectedEmail) {
    return (
      <div className="flex flex-col h-screen pt-20 bg-void">
        {/* Header */}
        <div className="bg-white/95 backdrop-blur-md border-b border-gray-200 px-6 py-4">
          <div className="max-w-7xl mx-auto">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-3">
                {/* Back Button */}
                <button
                  onClick={() => setViewMode("list")}
                  className="p-2 rounded-lg bg-primary/10 hover:bg-primary/20 border border-primary/20 transition-all duration-200 cursor-pointer"
                >
                  <X className="w-5 h-5 text-primary" />
                </button>

                <div>
                  <h1 className="font-semibold text-primary text-xl">
                    {selectedEmail.subject}
                  </h1>
                  <div className="flex items-center space-x-2 mt-1">
                    <span className="text-sm text-tertiary">
                      {selectedEmail.sender}
                    </span>
                    <span className="px-2 py-1 rounded-md text-xs font-medium flex items-center space-x-1">
                      {getPriorityIcon(selectedEmail.priority)}
                      <span className="uppercase">
                        {selectedEmail.priority}
                      </span>
                    </span>
                  </div>
                </div>
              </div>

              {/* Actions */}
              <div className="flex items-center space-x-2">
                <button
                  onClick={() => handleArchive(selectedEmail.id)}
                  className="px-4 py-2 rounded-lg bg-success/10 hover:bg-success/20 text-success font-medium border border-success/20 transition-all duration-200 cursor-pointer"
                >
                  <Archive className="w-4 h-4 inline mr-2" />
                  Archive
                </button>
                <button
                  onClick={() => handleDelete(selectedEmail.id)}
                  className="px-4 py-2 rounded-lg bg-error/10 hover:bg-error/20 text-error font-medium border border-error/20 transition-all duration-200 cursor-pointer"
                >
                  <Trash2 className="w-4 h-4 inline mr-2" />
                  Delete
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Email Content */}
        <div className="flex-1 overflow-auto">
          <div className="max-w-7xl mx-auto px-6 py-8">
            <div className="glass-card rounded-2xl p-8">
              {/* Sender Info */}
              <div className="flex items-start space-x-4 pb-6 border-b border-gray-200 mb-6">
                <div className="w-14 h-14 rounded-full bg-gradient-to-br from-violet-500/30 to-fuchsia-500/30 flex items-center justify-center">
                  <span className="text-xl font-bold text-white">
                    {selectedEmail.sender.charAt(0).toUpperCase()}
                  </span>
                </div>

                <div className="flex-1">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="font-semibold text-primary text-lg">
                        {selectedEmail.sender}
                      </div>
                      <div className="text-sm text-tertiary">
                        {selectedEmail.senderEmail}
                      </div>
                    </div>
                    <div className="text-sm text-tertiary">
                      {formatDate(selectedEmail.date)}
                    </div>
                  </div>
                </div>
              </div>

              {/* Email Body */}
              <div className="prose max-w-none">
                <div className="text-primary leading-relaxed">
                  {selectedEmail.body}
                </div>
              </div>

              {/* Action Items */}
              {selectedEmail.actionItems &&
                selectedEmail.actionItems.length > 0 && (
                  <div className="mt-8 pt-6 border-t border-gray-200">
                    <div className="font-semibold text-primary text-lg mb-4">
                      Action Items:
                    </div>
                    <div className="space-y-3">
                      {selectedEmail.actionItems.map((item, idx) => (
                        <div
                          key={idx}
                          className="flex items-start space-x-3 p-4 rounded-lg bg-accent-tertiary/5 border border-accent-tertiary/20"
                        >
                          <div className="flex-shrink-0 w-6 h-6 rounded-full bg-accent-tertiary/20 text-accent-tertiary flex items-center justify-center font-medium text-sm">
                            {idx + 1}
                          </div>
                          <div className="text-secondary flex-1">
                            {item}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
            </div>
          </div>
        </div>
      </div>
    );
  }

  return null;
}
