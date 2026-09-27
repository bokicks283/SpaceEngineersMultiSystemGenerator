using Sandbox.Game.Entities;
using Sandbox.ModAPI;
using System;
using System.Collections.Generic;
using System.Collections.Immutable;
using VRage;
using VRageMath;

namespace RandomSectorGenerator
{
    internal sealed class RealSolarSystemsClient
    {
        private const long Channel = 453273308835L;
        private bool _registered;
        private bool _apiInit;

        private Func<MyPlanet, MyTuple<bool, double, double>> _getBodyZoneRange;
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
            _convertPlanetPosToProxy = null;
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
