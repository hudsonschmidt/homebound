import SwiftUI
import AVFoundation

/// QR Code scanner view for scanning friend invite codes
struct QRScannerView: View {
    @Environment(\.dismiss) var dismiss
    let onCodeScanned: (String) -> Void

    @State private var isScanning = true
    @State private var scannedCode: String? = nil
    @State private var cameraPermissionGranted = false
    @State private var showingPermissionAlert = false

    var body: some View {
        NavigationStack {
            ZStack {
                if cameraPermissionGranted {
                    // Camera view
                    QRCodeScannerRepresentable(
                        isScanning: $isScanning,
                        onCodeScanned: handleCodeScanned
                    )
                    .ignoresSafeArea()

                    // Overlay with scanning frame
                    scannerOverlay
                } else {
                    // Permission needed view
                    permissionNeededView
                }
            }
            .navigationTitle("Scan QR Code")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Cancel") {
                        dismiss()
                    }
                    .foregroundStyle(.white)
                }
            }
            .toolbarBackground(.hidden, for: .navigationBar)
            .task {
                await checkCameraPermission()
            }
            .alert("Camera Access Required", isPresented: $showingPermissionAlert) {
                Button("Open Settings") {
                    if let settingsUrl = URL(string: UIApplication.openSettingsURLString) {
                        UIApplication.shared.open(settingsUrl)
                    }
                }
                Button("Cancel", role: .cancel) {
                    dismiss()
                }
            } message: {
                Text("Please allow camera access in Settings to scan QR codes.")
            }
        }
    }

    // MARK: - Scanner Overlay

    var scannerOverlay: some View {
        ZStack {
            // Semi-transparent background
            Color.black.opacity(0.5)
                .ignoresSafeArea()

            // Cutout for scanning area
            VStack(spacing: 24) {
                Spacer()

                // Scanning frame
                RoundedRectangle(cornerRadius: 24)
                    .stroke(Color.white, lineWidth: 3)
                    .frame(width: 250, height: 250)
                    .background(
                        RoundedRectangle(cornerRadius: 24)
                            .fill(Color.clear)
                    )
                    .overlay(
                        // Corner accents
                        cornerAccents
                    )

                // Instructions
                VStack(spacing: 8) {
                    Text("Point camera at QR code")
                        .font(.headline)
                        .foregroundStyle(.white)

                    Text("Position the friend's invite QR code within the frame")
                        .font(.subheadline)
                        .foregroundStyle(.white.opacity(0.7))
                        .multilineTextAlignment(.center)
                }
                .padding(.horizontal, 40)

                Spacer()
            }
        }
    }

    var cornerAccents: some View {
        GeometryReader { geometry in
            let size: CGFloat = 30
            let lineWidth: CGFloat = 4

            // Top-left corner
            Path { path in
                path.move(to: CGPoint(x: 0, y: size))
                path.addLine(to: CGPoint(x: 0, y: 0))
                path.addLine(to: CGPoint(x: size, y: 0))
            }
            .stroke(Color.hbBrand, lineWidth: lineWidth)

            // Top-right corner
            Path { path in
                path.move(to: CGPoint(x: geometry.size.width - size, y: 0))
                path.addLine(to: CGPoint(x: geometry.size.width, y: 0))
                path.addLine(to: CGPoint(x: geometry.size.width, y: size))
            }
            .stroke(Color.hbBrand, lineWidth: lineWidth)

            // Bottom-left corner
            Path { path in
                path.move(to: CGPoint(x: 0, y: geometry.size.height - size))
                path.addLine(to: CGPoint(x: 0, y: geometry.size.height))
                path.addLine(to: CGPoint(x: size, y: geometry.size.height))
            }
            .stroke(Color.hbBrand, lineWidth: lineWidth)

            // Bottom-right corner
            Path { path in
                path.move(to: CGPoint(x: geometry.size.width - size, y: geometry.size.height))
                path.addLine(to: CGPoint(x: geometry.size.width, y: geometry.size.height))
                path.addLine(to: CGPoint(x: geometry.size.width, y: geometry.size.height - size))
            }
            .stroke(Color.hbBrand, lineWidth: lineWidth)
        }
    }

    // MARK: - Permission Needed View

    var permissionNeededView: some View {
        VStack(spacing: 24) {
            Image(systemName: "camera.fill")
                .font(.system(size: 60))
                .foregroundStyle(.secondary)

            VStack(spacing: 8) {
                Text("Camera Access Needed")
                    .font(.title2)
                    .fontWeight(.bold)

                Text("To scan QR codes, please allow camera access in your device settings.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
            }

            Button(action: {
                if let settingsUrl = URL(string: UIApplication.openSettingsURLString) {
                    UIApplication.shared.open(settingsUrl)
                }
            }) {
                Label("Open Settings", systemImage: "gear")
                    .fontWeight(.semibold)
                    .foregroundStyle(.white)
                    .padding(.horizontal, 24)
                    .padding(.vertical, 12)
                    .background(Color.hbBrand)
                    .cornerRadius(12)
            }
        }
        .padding()
    }

    // MARK: - Actions

    func checkCameraPermission() async {
        let status = AVCaptureDevice.authorizationStatus(for: .video)

        switch status {
        case .authorized:
            await MainActor.run {
                cameraPermissionGranted = true
            }
        case .notDetermined:
            let granted = await AVCaptureDevice.requestAccess(for: .video)
            await MainActor.run {
                cameraPermissionGranted = granted
                if !granted {
                    showingPermissionAlert = true
                }
            }
        case .denied, .restricted:
            await MainActor.run {
                cameraPermissionGranted = false
                showingPermissionAlert = true
            }
        @unknown default:
            break
        }
    }

    func handleCodeScanned(_ code: String) {
        // Only process Homebound friend invite URLs
        guard code.contains("homeboundapp.com/f/") else {
            // Not a valid invite URL, keep scanning
            return
        }

        // Extract the token from the URL
        if let token = extractToken(from: code) {
            isScanning = false
            scannedCode = token
            onCodeScanned(token)
        }
    }

    func extractToken(from url: String) -> String? {
        // URL format: https://homeboundapp.com/f/{token}
        let pattern = "homeboundapp.com/f/([A-Za-z0-9_-]+)"
        guard let regex = try? NSRegularExpression(pattern: pattern),
              let match = regex.firstMatch(in: url, range: NSRange(url.startIndex..., in: url)),
              let tokenRange = Range(match.range(at: 1), in: url) else {
            return nil
        }
        return String(url[tokenRange])
    }
}

// MARK: - QR Code Scanner Representable

struct QRCodeScannerRepresentable: UIViewControllerRepresentable {
    @Binding var isScanning: Bool
    let onCodeScanned: (String) -> Void

    func makeUIViewController(context: Context) -> QRCodeScannerViewController {
        let controller = QRCodeScannerViewController()
        controller.delegate = context.coordinator
        return controller
    }

    func updateUIViewController(_ uiViewController: QRCodeScannerViewController, context: Context) {
        if isScanning {
            uiViewController.startScanning()
        } else {
            uiViewController.stopScanning()
        }
    }

    func makeCoordinator() -> Coordinator {
        Coordinator(onCodeScanned: onCodeScanned)
    }

    class Coordinator: NSObject, QRCodeScannerDelegate {
        let onCodeScanned: (String) -> Void

        init(onCodeScanned: @escaping (String) -> Void) {
            self.onCodeScanned = onCodeScanned
        }

        func didScanCode(_ code: String) {
            onCodeScanned(code)
        }
    }
}

// MARK: - QR Code Scanner View Controller

protocol QRCodeScannerDelegate: AnyObject {
    func didScanCode(_ code: String)
}

class QRCodeScannerViewController: UIViewController, AVCaptureMetadataOutputObjectsDelegate {
    weak var delegate: QRCodeScannerDelegate?

    private var captureSession: AVCaptureSession?
    private var previewLayer: AVCaptureVideoPreviewLayer?
    private var isSessionConfigured = false

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .black

        // Setup camera on background thread to avoid blocking UI
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            self?.setupCamera()
        }
    }

    override func viewDidLayoutSubviews() {
        super.viewDidLayoutSubviews()
        DispatchQueue.main.async { [weak self] in
            self?.previewLayer?.frame = self?.view.bounds ?? .zero
        }
    }

    func setupCamera() {
        // Check if we're on a simulator (no camera available)
        #if targetEnvironment(simulator)
        DispatchQueue.main.async { [weak self] in
            self?.showNoCameraLabel()
        }
        return
        #endif

        let captureSession = AVCaptureSession()

        guard let videoCaptureDevice = AVCaptureDevice.default(for: .video) else {
            DispatchQueue.main.async { [weak self] in
                self?.showNoCameraLabel()
            }
            return
        }

        let videoInput: AVCaptureDeviceInput
        do {
            videoInput = try AVCaptureDeviceInput(device: videoCaptureDevice)
        } catch {
            print("QRScanner: Failed to create video input: \(error)")
            return
        }

        if captureSession.canAddInput(videoInput) {
            captureSession.addInput(videoInput)
        } else {
            print("QRScanner: Cannot add video input")
            return
        }

        let metadataOutput = AVCaptureMetadataOutput()

        if captureSession.canAddOutput(metadataOutput) {
            captureSession.addOutput(metadataOutput)

            metadataOutput.setMetadataObjectsDelegate(self, queue: DispatchQueue.main)
            metadataOutput.metadataObjectTypes = [.qr]
        } else {
            print("QRScanner: Cannot add metadata output")
            return
        }

        let previewLayer = AVCaptureVideoPreviewLayer(session: captureSession)
        previewLayer.videoGravity = .resizeAspectFill

        DispatchQueue.main.async { [weak self] in
            guard let self = self else { return }
            previewLayer.frame = self.view.layer.bounds
            self.view.layer.addSublayer(previewLayer)
            self.previewLayer = previewLayer
        }

        self.captureSession = captureSession
        self.isSessionConfigured = true

        // Start running on background thread
        captureSession.startRunning()
    }

    private func showNoCameraLabel() {
        let label = UILabel()
        label.text = "Camera not available\n(Simulator)"
        label.textColor = .white
        label.textAlignment = .center
        label.numberOfLines = 2
        label.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(label)
        NSLayoutConstraint.activate([
            label.centerXAnchor.constraint(equalTo: view.centerXAnchor),
            label.centerYAnchor.constraint(equalTo: view.centerYAnchor)
        ])
    }

    func startScanning() {
        guard isSessionConfigured else { return }
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            if self?.captureSession?.isRunning == false {
                self?.captureSession?.startRunning()
            }
        }
    }

    func stopScanning() {
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            self?.captureSession?.stopRunning()
        }
    }

    func metadataOutput(_ output: AVCaptureMetadataOutput, didOutput metadataObjects: [AVMetadataObject], from connection: AVCaptureConnection) {
        if let metadataObject = metadataObjects.first,
           let readableObject = metadataObject as? AVMetadataMachineReadableCodeObject,
           let stringValue = readableObject.stringValue {

            // Haptic feedback
            UIImpactFeedbackGenerator(style: .medium).impactOccurred()

            delegate?.didScanCode(stringValue)
        }
    }
}

#Preview {
    QRScannerView { token in
        print("Scanned token: \(token)")
    }
}
