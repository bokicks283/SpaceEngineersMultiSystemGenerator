using Sandbox.Game.Entities;
using Sandbox.ModAPI;
using System;
using System.Collections.Generic;
using System.Collections.Immutable;
using VRageMath;

namespace RandomSectorGenerator
{
    internal sealed class RealGasGiantsClient
    {
        private const long Channel = 321421229679L;
        private bool _registered;
        private bool _apiInit;

        private Func<Vector3D, float, Vector3I, string, float, float, float, MyPlanet> _spawnGasGiant;
        private Func<MyPlanet, string, bool> _setGasGiantName;
        private Func<List<string>> _getGasGiantSkinList;

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
            _spawnGasGiant = null;
            _setGasGiantName = null;
            _getGasGiantSkinList = null;
        }

        public MyPlanet SpawnGasGiant(Vector3D position, float radiusKm, Vector3I color, string skin, float gravityStrength, float gravityFalloff, float dayLengthSeconds)
        {
            return _spawnGasGiant == null ? null : _spawnGasGiant(position, radiusKm, color, skin, gravityStrength, gravityFalloff, dayLengthSeconds);
        }

        public void SetGasGiantName(MyPlanet planet, string name)
        {
            if (_setGasGiantName != null && planet != null)
                _setGasGiantName(planet, name);
        }

        public List<string> GetSkins()
        {
            return _getGasGiantSkinList == null ? new List<string>() : (_getGasGiantSkinList() ?? new List<string>());
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
                _spawnGasGiant = (Func<Vector3D, float, Vector3I, string, float, float, float, MyPlanet>)methods["SpawnGasGiant"];
                _setGasGiantName = (Func<MyPlanet, string, bool>)methods["SetGasGiantConfig_Name"];
                _getGasGiantSkinList = (Func<List<string>>)methods["GetGasGiantSkinList"];
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
