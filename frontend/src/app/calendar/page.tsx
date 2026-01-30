"use client";

import { useState } from "react";
import {
  Calendar,
  Clock,
  MapPin,
  Users,
  CheckCircle,
  X,
  Plus,
  RefreshCw,
  ChevronLeft,
  ChevronRight,
  CalendarClock,
  AlertCircle,
  MoreVertical,
} from "lucide-react";

/**
 * Calendar/Events Interface
 * Modern glassmorphism design with proposal approval workflow
 * Includes upcoming events view and proposal management
 */
type CalendarEvent = {
  id: string;
  title: string;
  description: string;
  startTime: string;
  endTime: string;
  location: string;
  attendees: string[];
  status: "pending" | "approved" | "rejected" | "confirmed";
  source: "email" | "chat" | "manual";
  proposalSourceEmail?: string;
  color: string;
};

type CalendarView = "month" | "week" | "list";

const MOCK_EVENTS: CalendarEvent[] = [
  {
    id: "1",
    title: "Family Reunion Planning",
    description: "Final planning session for the upcoming family reunion. We'll cover venue confirmation, catering options, and travel arrangements.",
    startTime: "2025-01-25T14:00:00Z",
    endTime: "2025-01-25T15:30:00Z",
    location: "Family Home - Living Room",
    attendees: ["Sarah Johnson", "John Johnson", "Mike Johnson"],
    status: "pending",
    source: "email",
    proposalSourceEmail: "reunion-2025@family.com",
    color: "bg-purple-500/10 border-purple-500/30",
  },
  {
    id: "2",
    title: "Q4 Financial Review",
    description: "Quarterly portfolio review with investment advisor to discuss performance and strategy for the upcoming quarter.",
    startTime: "2025-01-26T10:00:00Z",
    endTime: "2025-01-26T11:30:00Z",
    location: "Video Call - Zoom",
    attendees: ["Investment Advisor", "Self"],
    status: "pending",
    source: "chat",
    color: "bg-blue-500/10 border-blue-500/30",
  },
  {
    id: "3",
    title: "Team Meeting - Weekly Sync",
    description: "Weekly team synchronization meeting to discuss project progress and blockers.",
    startTime: "2025-01-27T14:00:00Z",
    endTime: "2025-01-27T15:00:00Z",
    location: "Office - Conference Room A",
    attendees: ["Team Lead", "Product Manager", "Dev Team"],
    status: "confirmed",
    source: "manual",
    color: "bg-green-500/10 border-green-500/30",
  },
];

const MOCK_PROPOSALS: CalendarEvent[] = [
  {
    id: "p1",
    title: "Dinner Reservation - Restaurant",
    description: "Proposed dinner reservation at The Olive Garden for the family reunion.",
    startTime: "2025-01-25T18:00:00Z",
    endTime: "2025-01-25T20:00:00Z",
    location: "The Olive Garden - Main St",
    attendees: ["Sarah Johnson", "John Johnson", "Mike Johnson"],
    status: "pending",
    source: "email",
    proposalSourceEmail: "sarah.johnson@email.com",
    color: "bg-orange-500/10 border-orange-500/30",
  },
];

export default function CalendarPage() {
  const [events, setEvents] = useState<CalendarEvent[]>(MOCK_EVENTS);
  const [proposals, setProposals] = useState<CalendarEvent[]>(MOCK_PROPOSALS);
  const [viewMode, setViewMode] = useState<CalendarView>("list");
  const [loading, setLoading] = useState(false);
  const [selectedDate, setSelectedDate] = useState(new Date());
  const [currentMonth, setCurrentMonth] = useState(new Date());

  const handleApprove = (proposalId: string) => {
    setProposals((prev) =>
      prev.map((p) =>
        p.id === proposalId ? { ...p, status: "approved" as const } : p
      )
    );
  };

  const handleReject = (proposalId: string) => {
    setProposals((prev) =>
      prev.map((p) =>
        p.id === proposalId ? { ...p, status: "rejected" as const } : p
      )
    );
  };

  const handleRefresh = () => {
    setLoading(true);
    setTimeout(() => setLoading(false), 1000);
  };

  const formatTime = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleTimeString("en-US", {
      hour: "numeric",
      minute: "2-digit",
      hour12: true,
    });
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString("en-US", {
      weekday: "short",
      month: "short",
      day: "numeric",
    });
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case "pending":
        return "bg-orange-500/10 text-orange-500 border-orange-500/20";
      case "approved":
        return "bg-green-500/10 text-green-500 border-green-500/20";
      case "rejected":
        return "bg-red-500/10 text-red-500 border-red-500/20";
      case "confirmed":
        return "bg-blue-500/10 text-blue-500 border-blue-500/20";
      default:
        return "bg-gray-500/10 text-gray-500 border-gray-500/20";
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "pending":
        return <Clock className="w-4 h-4" />;
      case "approved":
        return <CheckCircle className="w-4 h-4" />;
      case "rejected":
        return <X className="w-4 h-4" />;
      case "confirmed":
        return <CalendarClock className="w-4 h-4" />;
      default:
        return <AlertCircle className="w-4 h-4" />;
    }
  };

  const getSourceIcon = (source: string) => {
    switch (source) {
      case "email":
        return (
          <div className="w-6 h-6 rounded-md bg-accent-primary/10 flex items-center justify-center">
            <span className="text-xs font-bold text-accent-primary">@</span>
          </div>
        );
      case "chat":
        return (
          <div className="w-6 h-6 rounded-md bg-accent-secondary/10 flex items-center justify-center">
            <span className="text-xs font-bold text-accent-secondary">AI</span>
          </div>
        );
      default:
        return (
          <div className="w-6 h-6 rounded-md bg-gray-500/10 flex items-center justify-center">
            <Calendar className="w-3 h-3 text-gray-500" />
          </div>
        );
    }
  };

  const EventsList = () => (
    <div className="space-y-4">
      {events.map((event) => (
        <div
          key={event.id}
          className={`glass-card rounded-2xl p-6 transition-all duration-200 hover:scale-[1.01] hover:shadow-lg ${event.color}`}
        >
          {/* Header */}
          <div className="flex items-start justify-between mb-4">
            <div className="flex items-center space-x-3">
              {/* Source Icon */}
              {getSourceIcon(event.source)}

              <div>
                <h3 className="font-semibold text-primary text-lg">
                  {event.title}
                </h3>
                <div className="flex items-center space-x-2 mt-1">
                  <span className="text-sm text-tertiary">
                    {formatDate(event.startTime)}
                  </span>
                  <span className={`px-2 py-1 rounded-md text-xs font-medium flex items-center space-x-1 ${getStatusColor(
                    event.status
                  )}`}
                  >
                    {getStatusIcon(event.status)}
                    <span className="uppercase">{event.status}</span>
                  </span>
                </div>
              </div>
            </div>

            {/* Actions */}
            <button className="p-2 rounded-lg bg-primary/10 hover:bg-primary/20 border border-primary/20 transition-all duration-200 cursor-pointer">
              <MoreVertical className="w-5 h-5 text-primary" />
            </button>
          </div>

          {/* Time & Location */}
          <div className="flex items-start space-x-6 mb-4">
            <div className="flex items-center space-x-2">
              <Clock className="w-4 h-4 text-tertiary" />
              <div>
                <div className="text-sm text-tertiary">
                  Start
                </div>
                <div className="font-medium text-primary">
                  {formatTime(event.startTime)}
                </div>
              </div>
            </div>
            <div className="flex items-center space-x-2">
              <Clock className="w-4 h-4 text-tertiary" />
              <div>
                <div className="text-sm text-tertiary">
                  End
                </div>
                <div className="font-medium text-primary">
                  {formatTime(event.endTime)}
                </div>
              </div>
            </div>
            <div className="flex items-center space-x-2">
              <MapPin className="w-4 h-4 text-tertiary" />
              <div className="text-sm font-medium text-primary">
                {event.location}
              </div>
            </div>
          </div>

          {/* Description */}
          {event.description && (
            <p className="text-secondary mb-4">
              {event.description}
            </p>
          )}

          {/* Attendees */}
          {event.attendees && event.attendees.length > 0 && (
            <div className="border-t border-gray-200 pt-3">
              <div className="flex items-center space-x-2 mb-2">
                <Users className="w-4 h-4 text-tertiary" />
                <span className="text-sm font-medium text-tertiary">
                  Attendees ({event.attendees.length})
                </span>
              </div>
              <div className="flex flex-wrap gap-2">
                {event.attendees.map((attendee, idx) => (
                  <span
                    key={idx}
                    className="px-3 py-1 rounded-md bg-primary/10 text-primary text-sm border border-primary/20"
                  >
                    {attendee}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      ))}
    </div>
  );

  const ProposalsSection = () => (
    <div className="space-y-4">
      <div className="flex items-center justify-between mb-2">
        <h2 className="font-semibold text-primary text-lg">
          Pending Proposals
        </h2>
        <span className="px-2 py-1 rounded-md bg-orange-500/10 text-orange-500 text-sm font-medium border border-orange-500/20">
          {proposals.length} Pending
        </span>
      </div>

      {proposals.map((proposal) => (
        <div
          key={proposal.id}
          className={`glass-card rounded-2xl p-6 transition-all duration-200 hover:scale-[1.01] hover:shadow-lg ${proposal.color}`}
        >
          {/* Header */}
          <div className="flex items-start justify-between mb-4">
            <div className="flex items-center space-x-3">
              {/* Source Icon */}
              {getSourceIcon(proposal.source)}

              <div>
                <h3 className="font-semibold text-primary text-lg">
                  {proposal.title}
                </h3>
                {proposal.proposalSourceEmail && (
                  <div className="text-sm text-tertiary">
                    From: {proposal.proposalSourceEmail}
                  </div>
                )}
              </div>
            </div>

            {/* Status Badge */}
            <span className={`px-2 py-1 rounded-md text-xs font-medium flex items-center space-x-1 ${getStatusColor(
              proposal.status
            )}`}
            >
              {getStatusIcon(proposal.status)}
              <span className="uppercase">{proposal.status}</span>
            </span>
          </div>

          {/* Time & Location */}
          <div className="flex items-start space-x-6 mb-4">
            <div className="flex items-center space-x-2">
              <Clock className="w-4 h-4 text-tertiary" />
              <div>
                <div className="text-sm text-tertiary">
                  {formatDate(proposal.startTime)}
                </div>
                <div className="font-medium text-primary">
                  {formatTime(proposal.startTime)} - {formatTime(proposal.endTime)}
                </div>
              </div>
            </div>
            <div className="flex items-center space-x-2">
              <MapPin className="w-4 h-4 text-tertiary" />
              <div className="text-sm font-medium text-primary">
                {proposal.location}
              </div>
            </div>
          </div>

          {/* Description */}
          {proposal.description && (
            <p className="text-secondary mb-4">
              {proposal.description}
            </p>
          )}

          {/* Action Buttons */}
          <div className="flex items-center justify-end space-x-3 pt-4 border-t border-gray-200">
            <button
              onClick={() => handleReject(proposal.id)}
              className="px-6 py-2 rounded-lg bg-error/10 hover:bg-error/20 text-error font-medium border border-error/20 transition-all duration-200 cursor-pointer"
            >
              Reject
            </button>
            <button
              onClick={() => handleApprove(proposal.id)}
              className="px-6 py-2 rounded-lg bg-success hover:bg-success/20 text-white font-medium border border-success/20 transition-all duration-200 cursor-pointer"
            >
              Approve
            </button>
          </div>
        </div>
      ))}

      {proposals.length === 0 && (
        <div className="flex flex-col items-center justify-center py-12">
          <CheckCircle className="w-16 h-16 text-success mb-4" />
          <h3 className="font-semibold text-primary text-lg mb-2">
            All proposals resolved
          </h3>
          <p className="text-secondary">
            No pending proposals at this time
          </p>
        </div>
      )}
    </div>
  );

  return (
    <div className="flex flex-col h-screen pt-20 bg-void">
      {/* Header */}
      <div className="bg-white/95 backdrop-blur-md border-b border-gray-200 px-6 py-4">
        <div className="max-w-7xl mx-auto">
          <div className="flex items-center justify-between">
            {/* Title */}
            <div>
              <h1 className="font-semibold text-primary text-xl">
                Calendar
              </h1>
              <p className="text-sm text-tertiary">
                Manage your events and proposals
              </p>
            </div>

            {/* Actions */}
            <div className="flex items-center space-x-3">
              {/* Add Event Button */}
              <button className="flex items-center space-x-2 px-4 py-2 rounded-lg bg-primary hover:bg-primary/90 text-white font-medium border border-primary/20 transition-all duration-200 cursor-pointer">
                <Plus className="w-5 h-5" />
                <span>Add Event</span>
              </button>

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

      {/* Content */}
      <div className="flex-1 overflow-auto">
        <div className="max-w-7xl mx-auto px-6 py-8">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
            {/* Events Column */}
            <div>
              <div className="flex items-center justify-between mb-4">
                <h2 className="font-semibold text-primary text-lg">
                  Upcoming Events
                </h2>
                <span className="px-2 py-1 rounded-md bg-blue-500/10 text-blue-500 text-sm font-medium border border-blue-500/20">
                  {events.length} Upcoming
                </span>
              </div>
              <EventsList />
            </div>

            {/* Proposals Column */}
            <div>
              <ProposalsSection />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
