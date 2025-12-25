//
//  Trip+Status.swift
//  Homebound
//
//  Extension for Trip status logic and computed properties
//

import Foundation

// MARK: - Trip Status Enum

/// Represents the possible states of a trip
enum TripStatus: String, CaseIterable {
    case active = "active"
    case overdue = "overdue"
    case overdueNotified = "overdue_notified"
    case completed = "completed"
    case planned = "planned"
    case scheduled = "scheduled"  // Kept for backwards compatibility
    case cancelled = "cancelled"

    /// Whether this status represents an "in progress" trip
    var isInProgress: Bool {
        switch self {
        case .active, .overdue, .overdueNotified:
            return true
        case .completed, .planned, .scheduled, .cancelled:
            return false
        }
    }

    /// Whether contacts have been notified
    var contactsNotified: Bool {
        self == .overdueNotified
    }

    /// User-facing display text
    var displayText: String {
        switch self {
        case .active:
            return "ACTIVE"
        case .overdue:
            return "CHECK IN NOW"
        case .overdueNotified:
            return "OVERDUE"
        case .completed:
            return "COMPLETED"
        case .planned:
            return "PLANNED"
        case .scheduled:
            return "SCHEDULED"
        case .cancelled:
            return "CANCELLED"
        }
    }
}

// MARK: - Trip Extension

extension Trip {

    /// The typed status of this trip
    var tripStatus: TripStatus {
        TripStatus(rawValue: status) ?? .active
    }

    /// Whether this trip is currently in progress (active, overdue, or overdue_notified)
    var isInProgress: Bool {
        tripStatus.isInProgress
    }

    /// Whether contacts have been notified about this trip being overdue
    var contactsNotified: Bool {
        tripStatus.contactsNotified
    }

    /// The deadline for this trip (ETA + grace period)
    var deadline: Date {
        eta_at.addingTimeInterval(TimeInterval(grace_minutes * 60))
    }

    /// Whether this trip is past its ETA
    var isPastETA: Bool {
        Date() > eta_at
    }

    /// Whether this trip is past its deadline (ETA + grace period)
    var isPastDeadline: Bool {
        Date() > deadline
    }

    /// Time remaining until ETA (negative if past)
    var timeRemaining: TimeInterval {
        eta_at.timeIntervalSince(Date())
    }

    /// Time remaining until deadline (negative if past)
    var timeRemainingUntilDeadline: TimeInterval {
        deadline.timeIntervalSince(Date())
    }

    /// Formatted time remaining string
    var formattedTimeRemaining: String {
        DateUtils.formatTimeRemaining(timeRemaining)
    }

    /// User-facing status text
    var statusDisplayText: String {
        if tripStatus == .active && isPastETA {
            return "CHECK IN NOW"  // In grace period
        }
        return tripStatus.displayText
    }

    /// Whether this trip should be considered "urgent" (past ETA or overdue)
    var isUrgent: Bool {
        isPastETA || tripStatus == .overdue || tripStatus == .overdueNotified
    }

    /// Whether check-in is available for this trip
    var canCheckIn: Bool {
        isInProgress && checkin_token != nil
    }

    /// Whether check-out is available for this trip
    var canCheckOut: Bool {
        isInProgress && checkout_token != nil
    }

    /// The number of contacts assigned to this trip
    var contactCount: Int {
        var count = 0
        if contact1 != nil { count += 1 }
        if contact2 != nil { count += 1 }
        if contact3 != nil { count += 1 }
        return count
    }

    /// The number of friend contacts assigned to this trip
    var friendContactCount: Int {
        var count = 0
        if friend_contact1 != nil { count += 1 }
        if friend_contact2 != nil { count += 1 }
        if friend_contact3 != nil { count += 1 }
        return count
    }

    /// Total number of contacts (regular + friend)
    var totalContactCount: Int {
        contactCount + friendContactCount
    }
}
