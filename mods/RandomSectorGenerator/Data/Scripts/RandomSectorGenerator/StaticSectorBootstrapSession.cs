using Sandbox.Definitions;
using Sandbox.Game.Entities;
using Sandbox.ModAPI;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using VRage.Game.Components;
using VRage.Game.ModAPI;
using VRage.ModAPI;
using VRage.Utils;
using VRageMath;

namespace RandomSectorGenerator
{
    // v0.3 bootstrap path. This deliberately stops before RSS adoption:
    // 1) spawn every celestial body as a normal static entity,
    // 2) write a deterministic hierarchy/orbit plan,
    // 3) let RSS discover those entities with /AddStrayPlanets.
    //
    // The older RandomSectorGeneratorSession remains installed for its diagnostics
    // and reference implementation, but this component claims fresh templates
    // before the legacy auto-generator can run.
    [MySessionComponentDescriptor(MyUpdateOrder.AfterSimulation)]
    public sealed class StaticSectorBootstrapSession : MySessionComponentBase
    {
        private const string Author = "Random Sector Generator";
        private const string ArmKey = "RSG_DisposableBootstrap_v1";
        private const string TemplateArmValue = "random-sector-template-v1";
        private const string ClaimedArmValue = "static-adoption-v1";
        private const string CompleteArmValue = "static-ready-v1";
        private const string StateFileName = "RandomSectorStaticBootstrap.State.xml";
        private const string PlanFileName = "RandomSectorStaticPlan.txt";
        private const string PlanTsvFileName = "RandomSectorStaticPlan.tsv";

        private const int MaximumPlanetDefinitions = 24;
        private const int VoxelMaterialSafetyBudget = 124;
        private const int TerminusDiameterKm = 500;
        private const double ParkingRadiusMin = 650000000d;
        private const double ParkingRadiusMax = 1125000000d;
        private const double ParkingSeparation = 30000000d;

        // Final intended RSS scale (meters). These are deliberately on the small
        // end of the large-sector design so jumps matter without making the sector
        // needlessly huge.
        private static readonly float[] StarOrbitMeters =
        {
            750000000f,   // Starter: 750,000 km
            1050000000f,  // Outer: 1,050,000 km
            1350000000f,  // Remote: 1,350,000 km
            250000000f    // Hostile Inner: 250,000 km
        };

        private static readonly string[] StarRoles =
        {
            "Starter",
            "Outer",
            "Remote",
            "Hostile Inner"
        };

        // Cinematic S-star cluster around Terminus. These intentionally use short
        // periods so their motion is visible from other systems rather than only
        // on multi-hour time scales.
        private static readonly float[] BlackHoleCompanionOrbitMeters =
        {
            20000000f, 35000000f, 55000000f
        };

        private static readonly float[] BlackHoleCompanionPeriodSeconds =
        {
            1200f, 2100f, 3600f
        };

        private static readonly Vector3I[] BlackHoleCompanionColors =
        {
            new Vector3I(190, 220, 255),
            new Vector3I(255, 185, 110),
            new Vector3I(255, 245, 225)
        };

        private static readonly HashSet<string> RequiredCustomPlanets = new HashSet<string>(
            CampaignPlanetPool.RequiredCustom, StringComparer.Ordinal);
        private static readonly HashSet<string> AllowedPlanets = new HashSet<string>(
            CampaignPlanetPool.RequiredCustom
                .Concat(CampaignPlanetPool.Vanilla)
                .Concat(CampaignPlanetPool.OptionalCustom),
            StringComparer.Ordinal);

        private static readonly HashSet<ulong> DeniedWorkshopIds = new HashSet<ulong>
        {
            2873186053UL, 2266665708UL, 2636128625UL, 2296726670UL, 2459246911UL,
            3617008256UL, 3617040986UL, 3618093811UL, 3617496051UL, 3561998389UL,
            2603627657UL, 2789619117UL
        };

        private readonly RealStarsClient _realStars = new RealStarsClient();
        private readonly RealGasGiantsClient _realGasGiants = new RealGasGiantsClient();
        private readonly List<Vector3D> _parkingPositions = new List<Vector3D>();
        private StaticBootstrapState _state = new StaticBootstrapState();
        private int _ticks;
        private bool _claimed;
        private bool _attempted;

        public override void LoadData()
        {
            _state = ReadState();
            _realStars.Load();
            _realGasGiants.Load();
        }

        protected override void UnloadData()
        {
            _realStars.Unload();
            _realGasGiants.Unload();
            _parkingPositions.Clear();
        }

        public override void UpdateAfterSimulation()
        {
            _ticks++;

            if (_ticks % 180 == 0)
            {
                if (!_realStars.IsReady && !_realStars.Compromised) _realStars.Load();
                if (!_realGasGiants.IsReady && !_realGasGiants.Compromised) _realGasGiants.Load();
            }

            if (!IsServer() || _state.Complete || _state.Failed)
                return;

            string armed;
            if (!_claimed && _ticks >= 60 && MyAPIGateway.Utilities.GetVariable(ArmKey, out armed))
            {
                if (string.Equals(armed, ClaimedArmValue, StringComparison.Ordinal))
                {
                    _claimed = true;
                }
                else if (string.Equals(armed, TemplateArmValue, StringComparison.Ordinal) ||
                         string.Equals(armed, "armed", StringComparison.Ordinal))
                {
                    MyAPIGateway.Utilities.SetVariable(ArmKey, ClaimedArmValue);
                    _claimed = true;
                    MyLog.Default.WriteLineAndConsole("[RSG Static] Claimed fresh Random Sector template.");
                }
            }

            if (!_attempted && _claimed && _ticks >= 600 &&
                _realStars.IsReady && _realGasGiants.IsReady)
            {
                _attempted = true;
                GenerateStaticSector(unchecked((int)DateTime.UtcNow.Ticks));
            }
        }

        private void GenerateStaticSector(int seed)
        {
            SectorBuild build = new SectorBuild(seed);
            try
            {
                foreach (var mod in MyAPIGateway.Session.Mods)
                {
                    if (DeniedWorkshopIds.Contains(mod.PublishedFileId))
                        throw new Exception("denylisted Workshop mod is active: " + mod.PublishedFileId);
                }

                int materialCount = MyDefinitionManager.Static.GetVoxelMaterialDefinitions()
                    .Select(x => x.Id.SubtypeName).Distinct().Count();
                if (materialCount > VoxelMaterialSafetyBudget)
                    throw new Exception("loaded voxel material count " + materialCount +
                        " exceeds safety budget " + VoxelMaterialSafetyBudget);

                List<MyPlanet> existing = GetLoadedPlanets();
                if (existing.Count > 0)
                    throw new Exception("fresh template already contains " + existing.Count + " planet/star entities");

                List<MyPlanetGeneratorDefinition> definitions = GetUsableDefinitions();
                HashSet<string> loaded = new HashSet<string>(
                    definitions.Select(x => x.Id.SubtypeId.ToString()), StringComparer.Ordinal);
                List<string> missing = RequiredCustomPlanets.Where(x => !loaded.Contains(x)).OrderBy(x => x).ToList();
                if (missing.Count > 0)
                    throw new Exception("required planet definitions are missing: " + string.Join(", ", missing));

                Shuffle(definitions, build.Random);
                if (definitions.Count > MaximumPlanetDefinitions)
                    definitions = definitions.Take(MaximumPlanetDefinitions).ToList();

                MyPlanetGeneratorDefinition starterDefinition = ChooseStarterDefinition(definitions);
                if (starterDefinition == null)
                    throw new Exception("no approved starter (Tellus or EarthLike) is available");
                definitions.Remove(starterDefinition);
                definitions.Insert(0, starterDefinition);

                MyPlanetGeneratorDefinition terminusDefinition = GetTerminusDefinition();
                if (terminusDefinition == null)
                    throw new Exception("Terminus planet definition is missing; Workshop 3481843850 must be active");

                List<string> skins = _realGasGiants.GetSkins();
                List<string> normalGasSkins = (skins ?? new List<string>())
                    .Where(x => !string.IsNullOrWhiteSpace(x) &&
                                x.IndexOf("blackhole", StringComparison.OrdinalIgnoreCase) < 0)
                    .ToList();

                BuildBodies(build, definitions, starterDefinition, terminusDefinition, normalGasSkins);

                if (build.Root == null || build.StarterPlanet == null || build.Stars.Count != 4 ||
                    build.BlackHoleCompanions.Count != 3)
                    throw new Exception("static sector did not produce Terminus, four systems, three S-stars, and starter");

                WritePlan(build);

                _state = new StaticBootstrapState
                {
                    Complete = true,
                    Seed = seed,
                    BodyCount = build.AllNodes.Count,
                    TerrestrialCount = definitions.Count + 1,
                    StarterName = build.StarterPlanet.Name,
                    StarterSubtype = starterDefinition.Id.SubtypeId.ToString(),
                    CreatedUtc = DateTime.UtcNow.ToString("o")
                };
                WriteState(_state);
                MyAPIGateway.Utilities.SetVariable(ArmKey, CompleteArmValue);

                Show("Static sector generated: 4 star systems + Terminus + 3 fast S-stars.");
                Show("All " + definitions.Count + " campaign worlds plus Terminus exist as real static planets.");
                Show("Setup character intentionally left at the original safe spawn. Do not use planetary respawn entries during bootstrap.");
                Show("SAVE and reload, run /AddStrayPlanets, then configure RSS from RandomSectorStaticPlan.tsv. Do not start survival yet.");
            }
            catch (Exception e)
            {
                MyLog.Default.WriteLineAndConsole("[RSG Static] Generation failed: " + e);
                Rollback(build);
                _state = new StaticBootstrapState { Failed = true, Seed = seed, Error = e.Message };
                try { WriteState(_state); } catch { }
                MyAPIGateway.Utilities.SetVariable(ArmKey, "failed");
                Show("Static sector generation failed. Restore the fresh Random Sector template and inspect SpaceEngineers.log.");
            }
        }

        private void BuildBodies(SectorBuild build, List<MyPlanetGeneratorDefinition> definitions,
            MyPlanetGeneratorDefinition starterDefinition, MyPlanetGeneratorDefinition terminusDefinition,
            List<string> normalGasSkins)
        {
            // Terminus is the physical central root. RSS adopts it like any other
            // planet while CampaignCelestialVisuals supplies a distant proxy disk.
            const string holeName = "Wyaris Abyss";
            build.UsedNames.Add("Wyaris");
            MyPlanet hole = SpawnPlanet(terminusDefinition, holeName, TerminusDiameterKm, build.Random);
            if (hole == null)
                throw new Exception("failed to spawn Terminus central black hole");
            build.GeneratedEntities.Add(hole);
            build.Root = new PlanNode(holeName, terminusDefinition.Id.SubtypeId.ToString(),
                hole.StorageName, "Central Black Hole", hole);

            // Three compact S-stars orbit Terminus quickly enough to visibly move
            // from distant systems. They intentionally do not own planets.
            for (int i = 0; i < BlackHoleCompanionOrbitMeters.Length; i++)
            {
                string name = "Wyaris S" + (i + 1) + " Star";
                float radiusKm = 26f + i * 5f;
                float brightness = 1.0f + (2 - i) * 0.2f;
                MyPlanet star = _realStars.SpawnStar(NextParkingPosition(build.Random), radiusKm,
                    BlackHoleCompanionColors[i], brightness, brightness,
                    radiusKm * 2.5f, 6f, 7f);
                if (star == null)
                    throw new Exception("Real Stars failed to spawn Terminus companion " + (i + 1));
                star.Name = name;
                _realStars.SetStarName(star, name);
                build.GeneratedEntities.Add(star);

                PlanNode node = new PlanNode(name, "RealStar", star.StorageName, "Black Hole Companion Star", star);
                SetFastCompanionOrbit(node, i, build.Random);
                AddChild(build.Root, node);
                build.BlackHoleCompanions.Add(node);
            }

            for (int i = 0; i < 4; i++)
            {
                string name = GenerateUniqueName(build) + " Star";
                float radiusKm = 90f + (float)build.Random.NextDouble() * 70f;
                float brightness = 0.9f + (float)build.Random.NextDouble() * 0.8f;
                MyPlanet star = _realStars.SpawnStar(NextParkingPosition(build.Random), radiusKm,
                    RandomStarColor(build.Random), brightness, brightness, radiusKm * 2.5f, 10f, 7f);
                if (star == null)
                    throw new Exception("Real Stars failed to spawn star " + i);
                star.Name = name;
                _realStars.SetStarName(star, name);
                build.GeneratedEntities.Add(star);

                PlanNode node = new PlanNode(name, "RealStar", star.StorageName, StarRoles[i] + " Star", star);
                SetOrbit(node, StarOrbitMeters[i], build.Random, 0.015f);
                AddChild(build.Root, node);
                build.Stars.Add(node);
            }

            // Two normal gas giants: one gives the hostile inner system a major
            // objective; the other gives an outer system more variety.
            if (normalGasSkins.Count > 0)
            {
                int[] hosts = { 3, 1 };
                for (int i = 0; i < hosts.Length; i++)
                {
                    int hostIndex = hosts[i];
                    string name = GenerateUniqueName(build) + " Giant";
                    string skin = normalGasSkins[build.Random.Next(normalGasSkins.Count)];
                    float radiusKm = 90f + (float)build.Random.NextDouble() * 70f;
                    MyPlanet giant = _realGasGiants.SpawnGasGiant(NextParkingPosition(build.Random), radiusKm,
                        new Vector3I(build.Random.Next(50, 240), build.Random.Next(50, 240), build.Random.Next(50, 240)),
                        skin, 4f, 3f, 7200f + build.Random.Next(0, 7200));
                    if (giant == null)
                        continue;
                    giant.Name = name;
                    _realGasGiants.SetGasGiantName(giant, name);
                    build.GeneratedEntities.Add(giant);

                    PlanNode node = new PlanNode(name, "RealGasGiant", giant.StorageName,
                        hostIndex == 3 ? "Hostile Gas Giant" : "Gas Giant", giant);
                    SetOrbit(node, NextPlanetOrbit(build.Stars[hostIndex], hostIndex == 3), build.Random, 0.04f);
                    AddChild(build.Stars[hostIndex], node);
                    build.GasGiants[hostIndex] = node;
                }
            }

            for (int i = 0; i < definitions.Count; i++)
            {
                MyPlanetGeneratorDefinition def = definitions[i];
                bool starter = def == starterDefinition;
                int starIndex = starter ? 0 : (i % 4);
                PlanNode star = build.Stars[starIndex];

                bool gasMoon = !starter && build.GasGiants.ContainsKey(starIndex) &&
                    build.Random.NextDouble() < (starIndex == 3 ? 0.35 : 0.25);
                bool planetMoon = !starter && !gasMoon && build.LastDirectPlanet.ContainsKey(starIndex) &&
                    build.Random.NextDouble() < 0.18;
                bool moon = gasMoon || planetMoon;

                int diameterKm = moon ? build.Random.Next(19, 41) : build.Random.Next(60, 121);
                string displayName = GenerateUniqueName(build);
                MyPlanet planet = SpawnPlanet(def, displayName, diameterKm, build.Random);
                if (planet == null)
                    throw new Exception("SpawnPlanet returned null for " + def.Id.SubtypeId);
                build.GeneratedEntities.Add(planet);

                string role = starter ? "Starter Planet" :
                    (starIndex == 3 ? (moon ? "Hostile Moon" : "Hostile Planet") : (moon ? "Moon" : "Planet"));
                PlanNode node = new PlanNode(displayName, def.Id.SubtypeId.ToString(), planet.StorageName, role, planet);

                if (gasMoon)
                {
                    PlanNode parent = build.GasGiants[starIndex];
                    SetOrbit(node, NextMoonOrbit(parent, build.Random), build.Random, 0.02f);
                    AddChild(parent, node);
                }
                else if (planetMoon)
                {
                    PlanNode parent = build.LastDirectPlanet[starIndex];
                    SetOrbit(node, NextMoonOrbit(parent, build.Random), build.Random, 0.015f);
                    AddChild(parent, node);
                }
                else
                {
                    SetOrbit(node, NextPlanetOrbit(star, starIndex == 3), build.Random,
                        starIndex == 3 ? 0.04f : 0.06f);
                    AddChild(star, node);
                    build.LastDirectPlanet[starIndex] = node;
                }

                build.AllNodes.Add(node);
                if (starter)
                    build.StarterPlanet = planet;
            }

            build.AllNodes.Insert(0, build.Root);
            build.AllNodes.InsertRange(1, build.BlackHoleCompanions);
            build.AllNodes.InsertRange(1 + build.BlackHoleCompanions.Count, build.Stars);
            foreach (PlanNode giant in build.GasGiants.Values)
                if (!build.AllNodes.Contains(giant)) build.AllNodes.Add(giant);
        }

        private MyPlanet SpawnPlanet(MyPlanetGeneratorDefinition def, string displayName, int diameterKm, Random rng)
        {
            float diameterMeters = diameterKm * 1000f;
            Vector3D center = NextParkingPosition(rng);
            float radius = diameterMeters * 0.5f;
            float boundingRadius = radius * (1f + Math.Max(0f, def.HillParams.Max));
            Vector3I boundingSize = VRage.Voxels.MyVoxelCoordSystems.FindBestOctreeSize(2f * boundingRadius);
            Vector3D spawnPosition = center - (Vector3D)boundingSize * 0.5d;

            IMyVoxelBase voxel = MyAPIGateway.Session.VoxelMaps.SpawnPlanet(
                def.Id.SubtypeId.ToString(), diameterMeters, rng.Next(1, int.MaxValue), spawnPosition);
            MyPlanet planet = voxel as MyPlanet;
            if (planet != null)
                planet.Name = displayName;
            return planet;
        }

        private static void AddChild(PlanNode parent, PlanNode child)
        {
            child.Parent = parent;
            parent.Children.Add(child);
        }

        private static void SetOrbit(PlanNode child, float semimajorAxis, Random rng, float maxEccentricity)
        {
            child.SemimajorAxis = semimajorAxis;
            child.Eccentricity = (float)(rng.NextDouble() * maxEccentricity);
            child.Pitch = (float)(rng.NextDouble() * 6d - 3d);
            child.Roll = (float)(rng.NextDouble() * 6d - 3d);
            child.Yaw = (float)(rng.NextDouble() * 360d);
            child.OrbitalPeriod = Math.Max(3600f, semimajorAxis / 400f);
            child.OrbitalPeriodOffset = (float)(rng.NextDouble() * Math.PI * 2d);
        }

        private static void SetFastCompanionOrbit(PlanNode child, int index, Random rng)
        {
            child.SemimajorAxis = BlackHoleCompanionOrbitMeters[index];
            child.Eccentricity = 0.02f + index * 0.03f;
            child.Pitch = new[] { 12f, -21f, 31f }[index];
            child.Roll = new[] { -8f, 17f, -26f }[index];
            child.Yaw = (float)(rng.NextDouble() * 360d);
            child.OrbitalPeriod = BlackHoleCompanionPeriodSeconds[index];
            child.OrbitalPeriodOffset = (float)(rng.NextDouble() * Math.PI * 2d);
        }

        private static float NextPlanetOrbit(PlanNode star, bool hostile)
        {
            int directChildren = star.Children.Count;
            if (hostile)
                return 4000000f + (directChildren + 1) * 7000000f; // ~11k-46k km
            return 6000000f + (directChildren + 1) * 9000000f;     // ~15k-60k km
        }

        private static float NextMoonOrbit(PlanNode parent, Random rng)
        {
            int index = parent.Children.Count + 1;
            return 300000f + index * 450000f + rng.Next(0, 250000); // ~750-1900 km
        }

        private Vector3D NextParkingPosition(Random rng)
        {
            for (int attempt = 0; attempt < 400; attempt++)
            {
                Vector3D dir = RandomUnitVector(rng);
                double radius = ParkingRadiusMin + rng.NextDouble() * (ParkingRadiusMax - ParkingRadiusMin);
                Vector3D candidate = dir * radius;
                bool clear = true;
                for (int i = 0; i < _parkingPositions.Count; i++)
                {
                    if (Vector3D.DistanceSquared(candidate, _parkingPositions[i]) <
                        ParkingSeparation * ParkingSeparation)
                    {
                        clear = false;
                        break;
                    }
                }
                if (clear)
                {
                    _parkingPositions.Add(candidate);
                    return candidate;
                }
            }
            throw new Exception("unable to allocate a separated static parking position");
        }

        private void WritePlan(SectorBuild build)
        {
            using (TextWriter writer = MyAPIGateway.Utilities.WriteFileInWorldStorage(
                PlanFileName, typeof(StaticSectorBootstrapSession)))
            {
                writer.WriteLine("Random Sector Generator - RSS adoption plan");
                writer.WriteLine("Seed: " + build.Seed);
                writer.WriteLine("Scale: Hostile Inner 250,000 km | Starter 750,000 km | Outer 1,050,000 km | Remote 1,350,000 km");
                writer.WriteLine("Workflow: save/reload -> /AddStrayPlanets -> save/exit -> apply this hierarchy to RSS -> /SetupRealOrbits -> Economy");
                writer.WriteLine();
                AppendPlan(writer, build.Root, "");
            }

            using (TextWriter writer = MyAPIGateway.Utilities.WriteFileInWorldStorage(
                PlanTsvFileName, typeof(StaticSectorBootstrapSession)))
            {
                writer.WriteLine("Role\tName\tPlanetType\tStorageName\tParent\tSemimajorAxisM\tEccentricity\tPitch\tRoll\tYaw\tOrbitalPeriodS\tOrbitalPeriodOffset");
                AppendTsv(writer, build.Root);
            }
        }

        private static void AppendPlan(TextWriter writer, PlanNode node, string indent)
        {
            if (node == null) return;
            string orbit = node.Parent == null ? "ROOT" :
                "a=" + (node.SemimajorAxis / 1000f).ToString("0") + " km period=" +
                node.OrbitalPeriod.ToString("0") + " s";
            writer.WriteLine(indent + node.Role + ": " + node.Name + " [" + node.PlanetType + "] " + orbit);
            for (int i = 0; i < node.Children.Count; i++)
                AppendPlan(writer, node.Children[i], indent + "  ");
        }

        private static void AppendTsv(TextWriter writer, PlanNode node)
        {
            if (node == null) return;
            writer.WriteLine(string.Join("\t", new[]
            {
                node.Role ?? "",
                node.Name ?? "",
                node.PlanetType ?? "",
                node.StorageName ?? "",
                node.Parent == null ? "" : node.Parent.Name,
                node.SemimajorAxis.ToString(System.Globalization.CultureInfo.InvariantCulture),
                node.Eccentricity.ToString(System.Globalization.CultureInfo.InvariantCulture),
                node.Pitch.ToString(System.Globalization.CultureInfo.InvariantCulture),
                node.Roll.ToString(System.Globalization.CultureInfo.InvariantCulture),
                node.Yaw.ToString(System.Globalization.CultureInfo.InvariantCulture),
                node.OrbitalPeriod.ToString(System.Globalization.CultureInfo.InvariantCulture),
                node.OrbitalPeriodOffset.ToString(System.Globalization.CultureInfo.InvariantCulture)
            }));
            for (int i = 0; i < node.Children.Count; i++)
                AppendTsv(writer, node.Children[i]);
        }

        private static void TeleportToStaticStarter(MyPlanet planet)
        {
            IMyCharacter character = MyAPIGateway.Session == null || MyAPIGateway.Session.Player == null
                ? null : MyAPIGateway.Session.Player.Character;
            if (character == null || planet == null) return;

            Vector3D center = ((IMyEntity)planet).WorldAABB.Center;
            double radius = ((IMyEntity)planet).WorldAABB.HalfExtents.Max();
            Vector3D probe = center + Vector3D.Up * (radius + 5000d);
            Vector3D surface = planet.GetClosestSurfacePointGlobal(probe);
            Vector3D up = Vector3D.Normalize(surface - center);
            Vector3D target = surface + up * 8d;
            character.Teleport(MatrixD.CreateWorld(target, Vector3D.CalculatePerpendicularVector(up), up), null, true);
            if (character.Physics != null)
            {
                character.Physics.LinearVelocity = Vector3.Zero;
                character.Physics.AngularVelocity = Vector3.Zero;
            }
        }

        private static List<MyPlanetGeneratorDefinition> GetUsableDefinitions()
        {
            return MyDefinitionManager.Static.GetPlanetsGeneratorsDefinitions()
                .Where(def =>
                {
                    if (def == null) return false;
                    string name = def.Id.SubtypeId.ToString();
                    if (string.IsNullOrWhiteSpace(name) || !AllowedPlanets.Contains(name)) return false;
                    string lower = name.ToLowerInvariant();
                    return !lower.Contains("tutorial") && !lower.Contains("example") &&
                           !lower.Contains("systemtest") && !lower.Contains("testmap");
                })
                .OrderBy(x => x.Id.SubtypeId.ToString(), StringComparer.OrdinalIgnoreCase)
                .ToList();
        }

        private static MyPlanetGeneratorDefinition GetTerminusDefinition()
        {
            List<MyPlanetGeneratorDefinition> candidates = MyDefinitionManager.Static.GetPlanetsGeneratorsDefinitions()
                .Where(def => def != null &&
                    def.Id.SubtypeId.ToString().IndexOf("Terminus", StringComparison.OrdinalIgnoreCase) >= 0)
                .OrderBy(def => def.Id.SubtypeId.ToString(), StringComparer.OrdinalIgnoreCase)
                .ToList();

            MyPlanetGeneratorDefinition exact = candidates.FirstOrDefault(def =>
                string.Equals(def.Id.SubtypeId.ToString(), "Terminus", StringComparison.OrdinalIgnoreCase));
            if (exact != null)
                return exact;
            if (candidates.Count == 1)
                return candidates[0];
            if (candidates.Count > 1)
                throw new Exception("multiple Terminus-like planet definitions are loaded: " +
                    string.Join(", ", candidates.Select(x => x.Id.SubtypeId.ToString())));
            return null;
        }

        private static MyPlanetGeneratorDefinition ChooseStarterDefinition(List<MyPlanetGeneratorDefinition> defs)
        {
            string[] preferred =
            {
                "Zenitaia",
                "Jormun",
                "Kerbin - Water Mod Ready",
                "Tellus",
                "EarthLike"
            };
            for (int i = 0; i < preferred.Length; i++)
            {
                MyPlanetGeneratorDefinition found = defs.FirstOrDefault(x =>
                    string.Equals(x.Id.SubtypeId.ToString(), preferred[i], StringComparison.Ordinal));
                if (found != null) return found;
            }
            return null;
        }

        private static void Shuffle<T>(IList<T> list, Random rng)
        {
            for (int i = list.Count - 1; i > 0; i--)
            {
                int j = rng.Next(i + 1);
                T tmp = list[i];
                list[i] = list[j];
                list[j] = tmp;
            }
        }

        private static Vector3D RandomUnitVector(Random rng)
        {
            double z = rng.NextDouble() * 2d - 1d;
            double theta = rng.NextDouble() * Math.PI * 2d;
            double planar = Math.Sqrt(Math.Max(0d, 1d - z * z));
            return new Vector3D(planar * Math.Cos(theta), z, planar * Math.Sin(theta));
        }

        private static Vector3I RandomStarColor(Random rng)
        {
            Vector3I[] palette =
            {
                new Vector3I(255, 244, 220), new Vector3I(255, 215, 170),
                new Vector3I(255, 180, 110), new Vector3I(210, 225, 255),
                new Vector3I(165, 195, 255), new Vector3I(255, 115, 80)
            };
            return palette[rng.Next(palette.Length)];
        }

        private static string GenerateUniqueName(SectorBuild build)
        {
            string[] a = { "Al", "Ca", "Da", "Eri", "Ka", "Lor", "Ny", "Or", "Pra", "Sa", "Tal", "Vex", "Wy", "Zen", "Ith", "Kor", "Mer", "Rho" };
            string[] b = { "dor", "ion", "ara", "eus", "eth", "ora", "yx", "aris", "une", "os", "ia", "eron", "alis", "orn", "ek", "uum" };
            for (int attempt = 0; attempt < 100; attempt++)
            {
                string candidate = a[build.Random.Next(a.Length)] + b[build.Random.Next(b.Length)];
                if (build.UsedNames.Add(candidate)) return candidate;
            }
            string fallback = "Body-" + build.UsedNames.Count;
            build.UsedNames.Add(fallback);
            return fallback;
        }

        private static List<MyPlanet> GetLoadedPlanets()
        {
            List<IMyVoxelBase> voxels = new List<IMyVoxelBase>();
            MyAPIGateway.Session.VoxelMaps.GetInstances(voxels, v => v is MyPlanet);
            return voxels.OfType<MyPlanet>().ToList();
        }

        private static bool IsServer()
        {
            return MyAPIGateway.Multiplayer == null || MyAPIGateway.Multiplayer.IsServer;
        }

        private static void Rollback(SectorBuild build)
        {
            for (int i = build.GeneratedEntities.Count - 1; i >= 0; i--)
            {
                try
                {
                    MyPlanet planet = build.GeneratedEntities[i];
                    if (planet != null && !planet.MarkedForClose) planet.Close();
                }
                catch { }
            }
        }

        private StaticBootstrapState ReadState()
        {
            try
            {
                if (!MyAPIGateway.Utilities.FileExistsInWorldStorage(StateFileName, typeof(StaticSectorBootstrapSession)))
                    return new StaticBootstrapState();
                using (TextReader reader = MyAPIGateway.Utilities.ReadFileInWorldStorage(
                    StateFileName, typeof(StaticSectorBootstrapSession)))
                {
                    StaticBootstrapState state = MyAPIGateway.Utilities.SerializeFromXML<StaticBootstrapState>(reader.ReadToEnd());
                    return state ?? new StaticBootstrapState();
                }
            }
            catch
            {
                return new StaticBootstrapState();
            }
        }

        private void WriteState(StaticBootstrapState state)
        {
            using (TextWriter writer = MyAPIGateway.Utilities.WriteFileInWorldStorage(
                StateFileName, typeof(StaticSectorBootstrapSession)))
                writer.Write(MyAPIGateway.Utilities.SerializeToXML(state));
        }

        private static void Show(string message)
        {
            if (MyAPIGateway.Utilities != null)
                MyAPIGateway.Utilities.ShowMessage(Author, message);
        }

        public sealed class StaticBootstrapState
        {
            public bool Complete;
            public bool Failed;
            public int Seed;
            public int BodyCount;
            public int TerrestrialCount;
            public string StarterName;
            public string StarterSubtype;
            public string CreatedUtc;
            public string Error;
        }

        private sealed class SectorBuild
        {
            public readonly int Seed;
            public readonly Random Random;
            public readonly List<MyPlanet> GeneratedEntities = new List<MyPlanet>();
            public readonly List<PlanNode> AllNodes = new List<PlanNode>();
            public readonly List<PlanNode> Stars = new List<PlanNode>();
            public readonly List<PlanNode> BlackHoleCompanions = new List<PlanNode>();
            public readonly Dictionary<int, PlanNode> GasGiants = new Dictionary<int, PlanNode>();
            public readonly Dictionary<int, PlanNode> LastDirectPlanet = new Dictionary<int, PlanNode>();
            public readonly HashSet<string> UsedNames = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            public PlanNode Root;
            public MyPlanet StarterPlanet;

            public SectorBuild(int seed)
            {
                Seed = seed;
                Random = new Random(seed);
            }
        }

        private sealed class PlanNode
        {
            public readonly string Name;
            public readonly string PlanetType;
            public readonly string StorageName;
            public readonly string Role;
            public readonly MyPlanet Entity;
            public readonly List<PlanNode> Children = new List<PlanNode>();
            public PlanNode Parent;
            public float SemimajorAxis;
            public float Eccentricity;
            public float Pitch;
            public float Roll;
            public float Yaw;
            public float OrbitalPeriod;
            public float OrbitalPeriodOffset;

            public PlanNode(string name, string planetType, string storageName, string role, MyPlanet entity)
            {
                Name = name;
                PlanetType = planetType;
                StorageName = storageName;
                Role = role;
                Entity = entity;
            }
        }
    }
}
