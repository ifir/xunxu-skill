import Foundation
import AVFoundation
import AppKit

// macOS 本机快速路径：avframes.swift <video> <outdir> [count]
let args = CommandLine.arguments
guard args.count >= 3 else {
    FileHandle.standardError.write("usage: avframes.swift <video> <outdir> [count]\n".data(using: .utf8)!)
    exit(2)
}
let source = URL(fileURLWithPath: args[1])
let output = URL(fileURLWithPath: args[2], isDirectory: true)
let count = max(1, min(Int(args.count >= 4 ? args[3] : "5") ?? 5, 9))
try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
let asset = AVURLAsset(url: source)
let duration = CMTimeGetSeconds(asset.duration)
guard duration.isFinite, duration > 0, !asset.tracks(withMediaType: .video).isEmpty else { exit(3) }
let generator = AVAssetImageGenerator(asset: asset)
generator.appliesPreferredTrackTransform = true
generator.maximumSize = CGSize(width: 1280, height: 1280)
generator.requestedTimeToleranceBefore = CMTime(value: 1, timescale: 10)
generator.requestedTimeToleranceAfter = CMTime(value: 1, timescale: 10)
for index in 0..<count {
    let ratio = count == 1 ? 0.5 : 0.05 + 0.90 * Double(index) / Double(count - 1)
    let requested = CMTime(seconds: duration * ratio, preferredTimescale: 600)
    do {
        var actual = CMTime.zero
        let image = try generator.copyCGImage(at: requested, actualTime: &actual)
        let data = NSBitmapImageRep(cgImage: image).representation(using: .png, properties: [:])!
        let target = output.appendingPathComponent(String(format: "frame-%02d.png", index + 1))
        try data.write(to: target)
        print("FRAME\t\(CMTimeGetSeconds(actual))\t\(target.path)")
    } catch {
        FileHandle.standardError.write("frame error: \(error.localizedDescription)\n".data(using: .utf8)!)
    }
}
