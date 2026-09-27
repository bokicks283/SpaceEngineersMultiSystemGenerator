using Sandbox.Definitions;
using Sandbox.Game.Entities;
using Sandbox.ModAPI;
using System;
using System.Collections.Generic;
using System.Linq;
using VRage.Game.Components;
using VRage.Game.ModAPI;
using VRage.ModAPI;
using VRageMath;
using VRage.Voxels;

namespace ProxyExportBootstrap
{
    [MySessionComponentDescriptor(MyUpdateOrder.AfterSimulation)]
    public sealed class ProxyExportBootstrapSession : MySessionComponentBase
    {
        private const string Author = "Proxy Export Bootstrap";
        private const string SpawnKey = "PEX_BootstrapSpawned_v1";
        private const float DiameterMeters = 120000f;

        private int _ticks;
        private bool _chatRegistered;
        private bool _spawnAttempted;

        private static readonly Dictionary<string, Vector3D> Centers =
            new Dictionary<string, Vector3D>(StringComparer.OrdinalIgnoreCase)
            {
                { "Zenitaia", new Vector3D(400000d, 0d, 0d) },
                { "Relicta", new Vector3D(-400000d, 0d, 0d) }
            };

        public override void UpdateAfterSimulation()
        {
            _ticks++;

            if (!_chatRegistered && MyAPIGateway.Utilities != null &&
                MyAPIGateway.Session != null && MyAPIGateway.Session.Player != null)
            {
                MyAPIGateway.Utilities.MessageEntered += OnMessageEntered;
                _chatRegistered = true;
            }

            if (!_spawnAttempted && _ticks >= 300 && IsServer())
            {
                _spawnAttempted = true;
                string state;
                if (!MyAPIGateway.Utilities.GetVariable(SpawnKey, out state) || state != "spawned")
                    SpawnExportPlanets();
            }
        }

        protected override void UnloadData()
        {
            if (_chatRegistered && MyAPIGateway.Utilities != null)
                MyAPIGateway.Utilities.MessageEntered -= OnMessageEntered;
            _chatRegistered = false;
        }

        private void SpawnExportPlanets()
        {
            try
            {
                var definitions = MyDefinitionManager.Static.GetPlanetsGeneratorsDefinitions()
                    .Where(x => Centers.ContainsKey(x.Id.SubtypeId.ToString()))
                    .ToDictionary(x => x.Id.SubtypeId.ToString(), StringComparer.OrdinalIgnoreCase);

                foreach (string name in Centers.Keys)
                    if (!definitions.ContainsKey(name))
                        throw new Exception("Planet definition is not loaded: " + name);

                foreach (string name in Centers.Keys)
                {
                    if (FindPlanet(name) != null)
                        continue;

                    MyPlanetGeneratorDefinition def = definitions[name];
                    Vector3D spawnPosition = CalculateSpawnPosition(def, DiameterMeters, Centers[name]);
                    int seed = (name.GetHashCode() & 0x7ffffffe) + 1;
                    IMyVoxelBase voxel = MyAPIGateway.Session.VoxelMaps.SpawnPlanet(
                        name, DiameterMeters, seed, spawnPosition);
                    MyPlanet planet = voxel as MyPlanet;
                    if (planet == null)
                        throw new Exception("SpawnPlanet returned null for " + name);
                    planet.Name = "PEX_" + name;
                }

                MyAPIGateway.Utilities.SetVariable(SpawnKey, "spawned");
                Show("Zenitaia and Relicta spawned at 120 km. Use /pex zenitaia or /pex relicta to move near either planet.");
                Focus("Zenitaia");
            }
            catch (Exception e)
            {
                Show("Bootstrap failed: " + e.Message + ". Exit and inspect SpaceEngineers.log.");
            }
        }

        private void OnMessageEntered(string messageText, ref bool sendToOthers)
        {
            if (string.IsNullOrWhiteSpace(messageText) ||
                !messageText.StartsWith("/pex", StringComparison.OrdinalIgnoreCase))
                return;

            sendToOthers = false;
            string[] parts = messageText.Trim().Split(new[] { ' ' }, StringSplitOptions.RemoveEmptyEntries);
            if (parts.Length == 1 || string.Equals(parts[1], "status", StringComparison.OrdinalIgnoreCase))
            {
                Show("Zenitaia=" + (FindPlanet("Zenitaia") != null ? "ready" : "missing") +
                     " | Relicta=" + (FindPlanet("Relicta") != null ? "ready" : "missing"));
                return;
            }

            if (string.Equals(parts[1], "zenitaia", StringComparison.OrdinalIgnoreCase))
            {
                Focus("Zenitaia");
                return;
            }

            if (string.Equals(parts[1], "relicta", StringComparison.OrdinalIgnoreCase))
            {
                Focus("Relicta");
                return;
            }

            Show("Commands: /pex status | /pex zenitaia | /pex relicta");
        }

        private void Focus(string name)
        {
            MyPlanet planet = FindPlanet(name);
            if (planet == null)
            {
                Show(name + " is not spawned.");
                return;
            }

            IMyCharacter character = MyAPIGateway.Session == null ||
                                     MyAPIGateway.Session.Player == null
                ? null
                : MyAPIGateway.Session.Player.Character;

            if (character == null)
            {
                Show(name + " center: " + ((IMyEntity)planet).WorldAABB.Center +
                     ". Move the spectator camera near this planet.");
                return;
            }

            Vector3D center = ((IMyEntity)planet).WorldAABB.Center;
            Vector3D radial = Vector3D.Up;
            double radius = ((IMyEntity)planet).WorldAABB.HalfExtents.Max();
            Vector3D probe = center + radial * (radius + 10000d);
            Vector3D surface = planet.GetClosestSurfacePointGlobal(probe);
            Vector3D destination = surface + radial * 5000d;
            Vector3D forward = Vector3D.CalculatePerpendicularVector(radial);

            character.Teleport(MatrixD.CreateWorld(destination, forward, radial), null, true);
            if (character.Physics != null)
            {
                character.Physics.LinearVelocity = Vector3.Zero;
                character.Physics.AngularVelocity = Vector3.Zero;
            }

            Show("Focused " + name + ". Planet Exporter commands now target this planet.");
        }

        private static MyPlanet FindPlanet(string subtype)
        {
            List<IMyVoxelBase> voxels = new List<IMyVoxelBase>();
            MyAPIGateway.Session.VoxelMaps.GetInstances(voxels, v => v is MyPlanet);
            string expectedName = "PEX_" + subtype;
            return voxels.OfType<MyPlanet>().FirstOrDefault(x =>
                string.Equals(x.Name, expectedName, StringComparison.OrdinalIgnoreCase));
        }

        private static Vector3D CalculateSpawnPosition(
            MyPlanetGeneratorDefinition def,
            float diameterMeters,
            Vector3D desiredCenter)
        {
            float radius = diameterMeters * 0.5f;
            float boundingRadius = radius * (1f + def.HillParams.Max);
            Vector3I boundingSize = MyVoxelCoordSystems.FindBestOctreeSize(2f * boundingRadius);
            return desiredCenter - (Vector3D)boundingSize * 0.5d;
        }

        private static bool IsServer()
        {
            return MyAPIGateway.Multiplayer == null || MyAPIGateway.Multiplayer.IsServer;
        }

        private static void Show(string message)
        {
            if (MyAPIGateway.Utilities != null)
                MyAPIGateway.Utilities.ShowMessage(Author, message);
        }
    }
}
