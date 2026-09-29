using Sandbox.Game.Entities;
using Sandbox.ModAPI;
using System;
using System.Collections.Generic;
using VRage.Game;
using VRage.Game.Components;
using VRage.ModAPI;
using VRage.Utils;
using VRageMath;
using BlendTypeEnum = VRageRender.MyBillboard.BlendTypeEnum;

namespace RandomSectorGenerator
{
    /// <summary>
    /// Client-only astronomical visual supplement.
    ///
    /// Real Stars intentionally stops its native glare at 200,000 km. The campaign
    /// spans roughly 1.35 million km from the central black hole, so remote stars
    /// otherwise disappear even though RSS still tracks them. This component draws
    /// tiny point-like stars using RSS proxy positions beyond the native glare range.
    ///
    /// The three Terminus companion stars are real Real Stars bodies and therefore
    /// use the same distant-star path. Terminus itself gets a lightweight distant
    /// accretion-disk/halo stand-in until RSS swaps to the real body.
    /// </summary>
    [MySessionComponentDescriptor(MyUpdateOrder.AfterSimulation)]
    public sealed class CampaignCelestialVisualsSession : MySessionComponentBase
    {
        private const double NativeGlareRangeM = 200000000d;
        private const double DistantStarFadeStartM = 175000000d;
        private const double DistantStarFullM = 225000000d;
        private const double DistantStarFarFadeStartM = 2500000000d;
        private const double DistantStarFarEndM = 3000000000d;

        // Keep distant stars on a relatively close camera shell. At the previous
        // 50 km shell their ~12 m minimum radius was sub-pixel at common FOVs,
        // which caused severe alias shimmer/flicker while the camera moved.
        private const double DistantStarRenderShellDistanceM = 20000d;
        private const float DistantStarMinimumRadius = 18f;
        private const float DistantStarMaximumRadius = 48f;

        private const double BlackHoleFarEndM = 3000000000d;
        private const double BlackHoleRenderShellDistanceM = 50000d;
        private const double TerminusDiskPhysicalRadiusM = 1250000d;
        private const float MinimumDiskRadius = 24f;
        private const float MaximumDiskRadius = 600f;

        private readonly RealStarsClient _realStars = new RealStarsClient();
        private readonly RealSolarSystemsClient _rss = new RealSolarSystemsClient();
        private readonly List<MyPlanet> _stars = new List<MyPlanet>();

        private readonly MyStringId _glowMaterial = MyStringId.GetOrCompute("SunBigGlow");
        private readonly MyStringId _rayMaterial = MyStringId.GetOrCompute("SunBigRays");
        private readonly MyStringId _dotMaterial = MyStringId.GetOrCompute("WhiteDot");

        private MyPlanet _blackHole;
        private int _ticks;

        public override void LoadData()
        {
            _realStars.Load();
            _rss.Load();
        }

        protected override void UnloadData()
        {
            _realStars.Unload();
            _rss.Unload();
            _stars.Clear();
            _blackHole = null;
        }

        public override void UpdateAfterSimulation()
        {
            if (MyAPIGateway.Utilities == null || MyAPIGateway.Utilities.IsDedicated ||
                MyAPIGateway.Session == null || MyAPIGateway.Session.Camera == null)
                return;

            _ticks++;

            if ((_ticks % 180) == 0)
            {
                if (!_realStars.IsReady && !_realStars.Compromised)
                    _realStars.Load();
                if (!_rss.IsReady && !_rss.Compromised)
                    _rss.Load();
            }

            if (!_realStars.IsReady || !_rss.IsReady)
                return;

            if ((_ticks % 600) == 1 || (_stars.Count == 0 && _ticks > 120))
                RefreshBodies();

            Vector3D proxyCamera = _rss.GetCurrentCameraProxyPosition();
            DrawRealStars(proxyCamera);
            DrawDistantBlackHole(proxyCamera);
        }

        private void RefreshBodies()
        {
            _stars.Clear();
            _blackHole = null;

            HashSet<IMyEntity> entities = new HashSet<IMyEntity>();
            MyAPIGateway.Entities.GetEntities(entities, entity => entity is MyPlanet);
            foreach (IMyEntity entity in entities)
            {
                MyPlanet planet = entity as MyPlanet;
                if (planet == null)
                    continue;

                float radiusKm;
                Vector3I color;
                float effectBrightness;
                float lightBrightness;
                float damageRadiusKm;
                if (_realStars.TryGetStarInfo(planet, out radiusKm, out color, out effectBrightness,
                    out lightBrightness, out damageRadiusKm))
                {
                    _stars.Add(planet);
                    continue;
                }

                if (!string.IsNullOrEmpty(planet.Name) &&
                    planet.Name.EndsWith(" Abyss", StringComparison.OrdinalIgnoreCase) &&
                    _rss.IsManagedBody(planet))
                {
                    _blackHole = planet;
                }
            }
        }

        private void DrawRealStars(Vector3D proxyCamera)
        {
            for (int i = 0; i < _stars.Count; i++)
            {
                MyPlanet star = _stars[i];
                if (star == null || !star.InScene)
                    continue;

                Vector3D proxyPosition;
                MatrixD proxyRotation;
                double surfaceRange;
                double orbitRange;
                if (!_rss.TryGetBodyProxyState(star, out proxyPosition, out proxyRotation, out surfaceRange, out orbitRange))
                    continue;

                Vector3D toStar = proxyPosition - proxyCamera;
                double distance = toStar.Length();
                if (distance <= DistantStarFadeStartM || distance >= DistantStarFarEndM)
                    continue;

                float radiusKm;
                Vector3I color;
                float effectBrightness;
                float lightBrightness;
                float damageRadiusKm;
                if (!_realStars.TryGetStarInfo(star, out radiusKm, out color, out effectBrightness,
                    out lightBrightness, out damageRadiusKm))
                    continue;

                float nearFade = SmoothStep((float)((distance - DistantStarFadeStartM) /
                    (DistantStarFullM - DistantStarFadeStartM)));
                float farFade = 1f;
                if (distance > DistantStarFarFadeStartM)
                {
                    farFade = 1f - SmoothStep((float)((distance - DistantStarFarFadeStartM) /
                        (DistantStarFarEndM - DistantStarFarFadeStartM)));
                }

                float fade = MathHelper.Clamp(nearFade * farFade, 0f, 1f);
                if (fade <= 0.001f)
                    continue;

                float brightness = MathHelper.Clamp(effectBrightness, 0.4f, 2f);
                float radius = (float)Math.Sqrt(NativeGlareRangeM / distance) * 44f;
                radius = MathHelper.Clamp(radius, DistantStarMinimumRadius, DistantStarMaximumRadius);

                Color drawColor = new Color(
                    (byte)MathHelper.Clamp(color.X, 0, 255),
                    (byte)MathHelper.Clamp(color.Y, 0, 255),
                    (byte)MathHelper.Clamp(color.Z, 0, 255));
                drawColor *= fade * MathHelper.Clamp(brightness / 1.5f, 0.45f, 1f);

                DrawPoint(proxyPosition, proxyCamera, drawColor, radius, true);
            }
        }

        private void DrawDistantBlackHole(Vector3D proxyCamera)
        {
            if (_blackHole == null || !_blackHole.InScene)
                return;

            Vector3D proxyPosition;
            MatrixD proxyRotation;
            double surfaceRange;
            double orbitRange;
            if (!_rss.TryGetBodyProxyState(_blackHole, out proxyPosition, out proxyRotation,
                out surfaceRange, out orbitRange))
                return;

            Vector3D toHole = proxyPosition - proxyCamera;
            double distance = toHole.Length();
            if (distance < 1d || distance >= BlackHoleFarEndM)
                return;

            // Once RSS hands us to the real Terminus orbit zone, its true 3D
            // accretion disk should be the only black-hole visual.
            if (orbitRange > 0d && distance <= orbitRange * 1.05d)
                return;

            double fadeSpan = Math.Max(5000000d, orbitRange * 0.5d);
            float nearFade = orbitRange <= 0d ? 1f : SmoothStep((float)(
                (distance - orbitRange * 1.05d) / fadeSpan));
            if (nearFade <= 0.001f)
                return;

            Vector3D direction = toHole / distance;
            MatrixD cameraMatrix = MyAPIGateway.Session.Camera.WorldMatrix;
            Vector3D drawPosition = cameraMatrix.Translation + direction * BlackHoleRenderShellDistanceM;

            float diskRadius = (float)(BlackHoleRenderShellDistanceM * TerminusDiskPhysicalRadiusM / distance);
            diskRadius = MathHelper.Clamp(diskRadius, MinimumDiskRadius, MaximumDiskRadius);

            // Keep the distant representation intentionally understated. It is a
            // proxy-space landmark, not a replacement for Terminus' actual 3D disk.
            Vector3 left = (Vector3)cameraMatrix.Left;
            Vector3 up = (Vector3)cameraMatrix.Up;
            Vector4 outer = new Vector4(1f, 0.24f, 0.035f, 1f) * (0.34f * nearFade);
            Vector4 inner = new Vector4(1f, 0.70f, 0.24f, 1f) * (1.25f * nearFade);
            Vector4 halo = new Vector4(1f, 0.40f, 0.08f, 1f) * (0.16f * nearFade);

            MyTransparentGeometry.AddBillboardOriented(
                _glowMaterial, halo, drawPosition, left, up, diskRadius * 1.6f,
                BlendTypeEnum.AdditiveBottom);
            MyTransparentGeometry.AddBillboardOriented(
                _dotMaterial, outer, drawPosition, left, up,
                diskRadius * 1.35f, diskRadius * 0.30f, Vector2.Zero,
                BlendTypeEnum.AdditiveBottom);
            MyTransparentGeometry.AddBillboardOriented(
                _dotMaterial, inner, drawPosition, left, up,
                diskRadius, diskRadius * 0.16f, Vector2.Zero,
                BlendTypeEnum.AdditiveBottom);
            MyTransparentGeometry.AddBillboardOriented(
                _dotMaterial, new Vector4(0f, 0f, 0f, 1f),
                drawPosition - direction * 2d, left, up,
                diskRadius * 0.28f, diskRadius * 0.20f, Vector2.Zero,
                BlendTypeEnum.Standard);
        }

        private void DrawPoint(Vector3D proxyTarget, Vector3D proxyCamera, Color color, float radius, bool addRays)
        {
            Vector3D direction = proxyTarget - proxyCamera;
            double length = direction.Normalize();
            if (length <= 1d || double.IsNaN(length))
                return;

            MatrixD cameraMatrix = MyAPIGateway.Session.Camera.WorldMatrix;
            Vector3D drawPosition = cameraMatrix.Translation + direction * DistantStarRenderShellDistanceM;
            Vector3 left = (Vector3)cameraMatrix.Left;
            Vector3 up = (Vector3)cameraMatrix.Up;

            // A small solid core keeps the star visible even when the soft glow
            // texture lands between screen pixels. The glow/rays then provide shape
            // without being responsible for the entire apparent brightness.
            Color core = color;
            core *= 1.15f;
            MyTransparentGeometry.AddBillboardOriented(
                _dotMaterial, core, drawPosition, left, up, radius * 0.42f,
                BlendTypeEnum.AdditiveBottom);

            MyTransparentGeometry.AddBillboardOriented(
                _glowMaterial, color, drawPosition, left, up, radius,
                BlendTypeEnum.AdditiveBottom);

            if (addRays)
            {
                Color rays = color;
                rays *= 0.18f;
                MyTransparentGeometry.AddBillboardOriented(
                    _rayMaterial, rays, drawPosition, left, up, radius * 1.5f,
                    BlendTypeEnum.AdditiveBottom);
            }
        }

        private static float SmoothStep(float value)
        {
            value = MathHelper.Clamp(value, 0f, 1f);
            return value * value * (3f - 2f * value);
        }

    }
}
