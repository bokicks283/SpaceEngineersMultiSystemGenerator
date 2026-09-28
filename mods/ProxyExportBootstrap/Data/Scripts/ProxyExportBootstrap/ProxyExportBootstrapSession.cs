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
        private const string SpawnKey = "PEX_BootstrapSpawned_v3";
        private const float DiameterMeters = 120000f;
        private const double TerminusCenterDistance = 10000000d;

        private int _ticks;
        private bool _chatRegistered;
        private bool _spawnAttempted;

        private static readonly Dictionary<string, Vector3D> Centers = BuildCenters();

        private static Dictionary<string, Vector3D> BuildCenters()
        {
            var result = new Dictionary<string, Vector3D>(StringComparer.OrdinalIgnoreCase);
            for (int i = 0; i < ProxyExportTargets.Names.Length; i++)
            {
                string name = ProxyExportTargets.Names[i];
                if (string.Equals(name, "Terminus (Black Hole)", StringComparison.OrdinalIgnoreCase))
                {
                    // Keep the black hole's enormous decorative cloud/disk layers
                    // isolated from the ordinary planet export stations.
                    result.Add(name, new Vector3D(TerminusCenterDistance, 0d, 0d));
                    continue;
                }

                double distance = 400000d * (i / 2 + 1);
                double x = i % 2 == 0 ? distance : -distance;
                result.Add(name, new Vector3D(x, 0d, 0d));
            }
            return result;
        }

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
                if (Centers.Count == 0)
                {
                    Show("Every selected planet already has an active proxy.");
                    return;
                }
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
                Show("Export planets ready: " + string.Join(", ", Centers.Keys) + ". Use /pex status and /pex <name>.");
                Focus(ProxyExportTargets.Names[0]);
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
            string command = messageText.Trim().Substring(4).Trim();
            if (command.Length == 0 || string.Equals(command, "status", StringComparison.OrdinalIgnoreCase))
            {
                Show(string.Join(" | ", Centers.Keys.Select(name =>
                    name + "=" + (FindPlanet(name) != null ? "ready" : "missing"))));
                return;
            }

            string[] matches = Centers.Keys.Where(name =>
                string.Equals(name, command, StringComparison.OrdinalIgnoreCase) ||
                name.StartsWith(command + " ", StringComparison.OrdinalIgnoreCase)).ToArray();
            if (matches.Length == 1)
            {
                Focus(matches[0]);
                return;
            }

            Show("Commands: /pex status | /pex <name>. Targets: " + string.Join(", ", Centers.Keys));
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
