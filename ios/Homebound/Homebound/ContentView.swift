//
//  ContentView.swift
//  Homebound
//
//  Created by Hudson Schmidt on 10/23/25.
//

import SwiftUI

struct ContentView: View {
    @EnvironmentObject var session: Session

    var body: some View {
        Group {
            if session.isAuthenticated {
                LandingView()
            } else {
                SignInView()
            }
        }
    }
}
