using Sandbox.Game.Entities;
using Sandbox.ModAPI;
using System;
using System.Collections.Generic;
using System.Collections.Immutable;
using VRageMath;

namespace RandomSectorGenerator
{
    internal sealed class RealStarsClient
    {
        private const long Channel = 635917436927L;
        private bool _registered;
        private bool _apiInit;

        private Func<Vector3D, float, Vector3I, float, float, float, float, float, MyPlanet> _spawnStar;
        private Func<MyPlanet, string, bool> _setStarName;

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
            _spawnStar = null;
            _setStarName = null;
        }

        public MyPlanet SpawnStar(Vector3D position, float radiusKm, Vector3I color, float effectBrightness, float lightBrightness, float damageRadiusKm, float gravityStrength, float gravityFalloff)
        {
            return _spawnStar == null ? null : _spawnStar(position, radiusKm, color, effectBrightness, lightBrightness, damageRadiusKm, gravityStrength, gravityFalloff);
        }

        public void SetStarName(MyPlanet planet, string name)
        {
            if (_setStarName != null && planet != null)
                _setStarName(planet, name);
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
                _spawnStar = (Func<Vector3D, float, Vector3I, float, float, float, float, float, MyPlanet>)methods["SpawnStar"];
                _setStarName = (Func<MyPlanet, string, bool>)methods["SetStarName"];
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
