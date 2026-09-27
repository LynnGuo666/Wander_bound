import CoreLocation
import Foundation

final class LocationService: NSObject, ObservableObject, CLLocationManagerDelegate {
    @Published var coordinate: CLLocationCoordinate2D?
    @Published var message = "点击获取坐标；地点服务可反查出发城市"
    private let manager = CLLocationManager()

    override init() {
        super.init()
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyKilometer
    }

    func locate() {
        switch manager.authorizationStatus {
        case .notDetermined:
            message = "等待位置权限…"
            manager.requestWhenInUseAuthorization()
        case .authorizedWhenInUse, .authorizedAlways:
            message = "正在获取位置…"
            manager.requestLocation()
        default:
            message = "定位不可用，请手动输入出发城市"
        }
    }

    func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        if manager.authorizationStatus == .authorizedWhenInUse || manager.authorizationStatus == .authorizedAlways {
            manager.requestLocation()
        }
    }

    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard let location = locations.last else { return }
        coordinate = location.coordinate
        message = "坐标已获取 · 配置地点服务后识别城市"
    }

    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        message = "定位失败，请手动输入出发城市"
    }
}
