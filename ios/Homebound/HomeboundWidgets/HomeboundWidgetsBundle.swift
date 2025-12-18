//
//  HomeboundWidgetsBundle.swift
//  HomeboundWidgets
//
//  Created by Hudson Schmidt on 12/16/25.
//

import WidgetKit
import SwiftUI

@main
struct HomeboundWidgetsBundle: WidgetBundle {
    var body: some Widget {
        // Live Activity
        TripLiveActivity()

        // Home Screen Widgets
        SmallTripWidget()
        MediumTripWidget()

        // Lock Screen Widgets
        LockScreenCircularWidget()
        LockScreenInlineWidget()
        LockScreenRectangularWidget()
    }
}
