using ProtoBuf;
using System.Collections.Generic;
using VRageMath;

namespace RandomSectorGenerator
{
    // Wire-compatible subset of Real Solar Systems' protobuf config types.
    // Field numbers intentionally match RSS exactly. We only serialize fields
    // required to bootstrap a sector; RSS fills the omitted/default fields.

    [ProtoContract(UseProtoMembersOnly = true)]
    public sealed class RssSettingsWire
    {
        [ProtoMember(1)] public bool OverrideFromConfig = false;
        [ProtoMember(2)] public float GlobalTimescale = 1f;
        [ProtoMember(3)] public Vector3D VoxelPlanetSpawnCenter = Vector3D.Zero;
        [ProtoMember(4)] public float VoxelPlanetSpawnRangeMin = 600000f;
        [ProtoMember(5)] public float VoxelPlanetSpawnRangeMax = 1200000f;
        [ProtoMember(11)] public float GlobalSpeedLimit = -1f;
        [ProtoMember(12)] public float GlobalOrbitSpeedLimit = -1f;
        [ProtoMember(13)] public float GlobalSurfaceSpeedLimit = -1f;
        [ProtoMember(6)] public List<RssSolarSystemWire> SolarSystems = new List<RssSolarSystemWire>();
    }

    [ProtoContract(UseProtoMembersOnly = true)]
    public sealed class RssSolarSystemWire
    {
        [ProtoMember(1)] public Vector3D Position;
        [ProtoMember(2)] public RssBodyWire RootBody;
    }

    [ProtoContract(UseProtoMembersOnly = true)]
    public sealed class RssBodyWire
    {
        [ProtoMember(1)] public string BodyInstanceName = "None";
        [ProtoMember(2)] public string Name;
        [ProtoMember(3)] public string PlanetTypeId;
        [ProtoMember(4)] public float PlanetOrbitZoneRadius;
        [ProtoMember(5)] public float PlanetProxyScale = 1f;
        [ProtoMember(6)] public bool AsteroidsEnabled = true;
        [ProtoMember(15)] public float CustomOrbitSpeedLimit = -1f;
        [ProtoMember(16)] public float CustomSurfaceSpeedLimit = -1f;
        [ProtoMember(17)] public long EmptyZoneFakeId = -1;
        [ProtoMember(7)] public RssTerrestrialWire TerrestrialPlanetInfo;
        [ProtoMember(8)] public RssOrbitWire OrbitInfo;
        [ProtoMember(12)] public float SiblingWeight = -1f;
        [ProtoMember(13)] public RssBodyWire Sibling;
        [ProtoMember(14)] public List<RssBodyWire> Children = new List<RssBodyWire>();
    }

    [ProtoContract(UseProtoMembersOnly = true)]
    public sealed class RssTerrestrialWire
    {
        [ProtoMember(1)] public float RadiusKm;
        [ProtoMember(2)] public float PlanetSurfaceZoneRadius;
        [ProtoMember(3)] public float PlanetProxyFadeoutHeightMult = 0f;
        [ProtoMember(4)] public float PlanetRotationPeriod;
        [ProtoMember(5)] public float PlanetRotationPeriodOffset;
        [ProtoMember(6)] public string ProxySkinOverride;
        [ProtoMember(7)] public float GravityStrength = -1f;
        [ProtoMember(8)] public float GravityFalloff = -1f;
    }

    [ProtoContract(UseProtoMembersOnly = true)]
    public sealed class RssOrbitWire
    {
        [ProtoMember(1)] public float SemimajorAxis = 1000000f;
        [ProtoMember(2)] public float Eccentricity = 0f;
        [ProtoMember(3)] public float Pitch = 0f;
        [ProtoMember(4)] public float Roll = 0f;
        [ProtoMember(5)] public float Yaw = 0f;
        [ProtoMember(6)] public float OrbitalPeriod = 30f;
        [ProtoMember(7)] public float OrbitalPeriodOffset = 0f;
    }

    public sealed class PendingSectorState
    {
        public bool InProgress;
        public bool Failed;
        public List<long> GeneratedEntityIds = new List<long>();
        public bool PendingApply;
        public bool Applied;
        public int Seed;
        public int StellarSystemCount;
        public int PlanetDefinitionCount;
        public int GeneratedGasGiants;
        public bool GeneratedBlackHole;
        public string BlackHoleSkin;
        public string StartPlanetDisplayName;
        public string StartPlanetSubtype;
        public long StartPlanetEntityId;
        public string StartPlanetStorageName;
        public string RssConfigBase64;
        public string CreatedUtc;
    }
}
