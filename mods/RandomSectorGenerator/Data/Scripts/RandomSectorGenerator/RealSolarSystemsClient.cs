using Sandbox.Game.Entities;
using Sandbox.ModAPI;
using System;
using System.Collections.Generic;
using System.Collections.Immutable;
using VRage;
using VRage.ModAPI;
using VRageMath;

namespace RandomSectorGenerator
{
    internal sealed class RealSolarSystemsClient
    {
        private const long Channel = 453273308835L;
        private bool _registered;
        private bool _apiInit;

        private Func<MyPlanet, MyTuple<bool, double, double>> _getBodyZoneRange;
        private Func<Vector3D> _getCurrentCameraPos;
        private Func<Vector3D, Vector3D> _convertRealPosToProxy;
        private Func<MyPlanet, Vector3D> _getBodyProxyPosition;
        private Func<MyPlanet, MatrixD> _getBodyProxyRotation;
        private Func<IMyEntity, MyTuple<bool, MyPlanet, bool>> _getEntityZone;
        private Func<MyPlanet, bool, Vector3D, Vector3D> _convertPlanetPosToProxy;

        public bool IsReady { get; private set; }
        public bool Compromised { get; private set; }

        public void Load()
        {
            if (!_registered && MyAPIGateway.Utilities != null)
            {
                MyAPIGateway.Utilities.RegisterMessageHandler(Channel, HandleMessage);
                _registered = true;
            }

            if (_registered && !IsReady)
                MyAPIGateway.Utilities.SendModMessage(Channel, "ApiEndpointRequest");
        }

        public void Unload()
        {
            if (_registered && MyAPIGateway.Utilities != null)
                MyAPIGateway.Utilities.UnregisterMessageHandler(Channel, HandleMessage);

            _registered = false;
            _apiInit = false;
            IsReady = false;
            Compromised = false;
            _getBodyZoneRange = null;
            _getCurrentCameraPos = null;
            _convertRealPosToProxy = null;
            _getBodyProxyPosition = null;
            _getBodyProxyRotation = null;
            _getEntityZone = null;
            _convertPlanetPosToProxy = null;
        }

        public Vector3D GetCurrentCameraProxyPosition()
        {
            if (!IsReady || Compromised)
                return GetFallbackCameraPosition();

            try
            {
                // RSS's GetCurrentCameraPos already returns the camera in the
                // current logical/proxy coordinate frame. Converting it again via
                // ConvertRealPosToProxy double-transforms the camera and makes
                // nearby bodies appear astronomically far away to visual helpers.
                if (_getCurrentCameraPos != null)
                    return _getCurrentCameraPos();

                // Fallback for an older/incomplete endpoint: only convert the raw
                // Space Engineers camera position when RSS does not provide its
                // own logical camera position.
                Vector3D current = GetFallbackCameraPosition();
                return _convertRealPosToProxy == null ? current : _convertRealPosToProxy(current);
            }
            catch
            {
                IsReady = false;
                return GetFallbackCameraPosition();
            }
        }

        private static Vector3D GetFallbackCameraPosition()
        {
            if (MyAPIGateway.Session == null || MyAPIGateway.Session.Camera == null)
                return Vector3D.Zero;
            return MyAPIGateway.Session.Camera.Position;
        }

        public bool TryGetBodyProxyState(MyPlanet planet, out Vector3D position, out MatrixD rotation, out double surfaceZoneRange, out double orbitZoneRange)
        {
            position = Vector3D.Zero;
            rotation = MatrixD.Identity;
            surfaceZoneRange = 0d;
            orbitZoneRange = 0d;
            if (!IsReady || Compromised || planet == null || _getBodyProxyPosition == null ||
                _getBodyProxyRotation == null || _getBodyZoneRange == null)
                return false;

            try
            {
                MyTuple<bool, double, double> range = _getBodyZoneRange(planet);
                if (!range.Item1)
                    return false;
                position = _getBodyProxyPosition(planet);
                rotation = _getBodyProxyRotation(planet);
                surfaceZoneRange = range.Item2;
                orbitZoneRange = range.Item3;
                return true;
            }
            catch
            {
                IsReady = false;
                return false;
            }
        }

        public bool TryGetEntityZone(IMyEntity entity, out MyPlanet planet, out bool isSurface)
        {
            planet = null;
            isSurface = false;
            if (!IsReady || Compromised || entity == null || _getEntityZone == null)
                return false;

            try
            {
                MyTuple<bool, MyPlanet, bool> zone = _getEntityZone(entity);
                planet = zone.Item2;
                isSurface = zone.Item3;
                return zone.Item1;
            }
            catch
            {
                IsReady = false;
                return false;
            }
        }

        public bool IsManagedBody(MyPlanet planet)
        {
            if (!IsReady || Compromised || planet == null || _getBodyZoneRange == null)
                return false;

            try
            {
                MyTuple<bool, double, double> info = _getBodyZoneRange(planet);
                return info.Item1;
            }
            catch
            {
                IsReady = false;
                return false;
            }
        }

        public bool TryConvertSurfaceToProxy(MyPlanet planet, Vector3D trueSurfacePosition, out Vector3D proxyPosition)
        {
            proxyPosition = trueSurfacePosition;
            if (!IsReady || Compromised || planet == null || _convertPlanetPosToProxy == null)
                return false;

            try
            {
                proxyPosition = _convertPlanetPosToProxy(planet, true, trueSurfacePosition);
                return true;
            }
            catch
            {
                IsReady = false;
                return false;
            }
        }

        private void HandleMessage(object message)
        {
            if (_apiInit)
                return;

            string status = message as string;
            if (string.Equals(status, "Compromised", StringComparison.Ordinal))
            {
                Compromised = true;
                IsReady = false;
                return;
            }

            IReadOnlyDictionary<string, Delegate> methods = message as IReadOnlyDictionary<string, Delegate>;
            if (methods == null || methods is ImmutableDictionary<string, Delegate>)
                return;

            // Mirror the upstream API client's tamper-check handshake before binding delegates.
            var builder = ImmutableDictionary.CreateBuilder<string, Delegate>();
            foreach (var pair in methods)
                builder.Add(pair.Key, pair.Value);
            MyAPIGateway.Utilities.SendModMessage(Channel, builder.ToImmutable());

            try
            {
                _getBodyZoneRange = (Func<MyPlanet, MyTuple<bool, double, double>>)methods["GetBodyZoneRange"];
                _getCurrentCameraPos = (Func<Vector3D>)methods["GetCurrentCameraPos"];
                _convertRealPosToProxy = (Func<Vector3D, Vector3D>)methods["ConvertRealPosToProxy"];
                _getBodyProxyPosition = (Func<MyPlanet, Vector3D>)methods["GetBodyProxyPosition"];
                _getBodyProxyRotation = (Func<MyPlanet, MatrixD>)methods["GetBodyProxyRotation"];
                _getEntityZone = (Func<IMyEntity, MyTuple<bool, MyPlanet, bool>>)methods["GetEntityZone"];
                _convertPlanetPosToProxy = (Func<MyPlanet, bool, Vector3D, Vector3D>)methods["ConvertPlanetPosToProxy"];
                _apiInit = true;
                IsReady = true;
            }
            catch
            {
                IsReady = false;
            }
        }
    }
}
