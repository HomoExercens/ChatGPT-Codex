export type UaDataBrandMajor = {
  brand: string;
  major: string;
};

export type UaDataLowEntropy = {
  uach_available: boolean;
  uaData_platform: string | null;
  uaData_mobile: boolean | null;
  uaData_brands_major: UaDataBrandMajor[] | null;
};

function safeBrandMajor(raw: unknown): UaDataBrandMajor | null {
  if (!raw || typeof raw !== 'object') return null;
  const brand = String((raw as any).brand ?? '').trim();
  const version = String((raw as any).version ?? '').trim();
  if (!brand) return null;
  const major = (version.split('.')[0] || '').trim();
  if (!major) return null;
  if (!/^[0-9]{1,4}$/.test(major)) return null;
  return { brand: brand.slice(0, 64), major };
}

export function getUaDataLowEntropy(): UaDataLowEntropy {
  if (typeof navigator === 'undefined') {
    return {
      uach_available: false,
      uaData_platform: null,
      uaData_mobile: null,
      uaData_brands_major: null,
    };
  }

  const uaData = (navigator as any).userAgentData;
  if (!uaData) {
    return {
      uach_available: false,
      uaData_platform: null,
      uaData_mobile: null,
      uaData_brands_major: null,
    };
  }

  const platformRaw = uaData.platform;
  const mobileRaw = uaData.mobile;
  const brandsRaw = uaData.brands;

  const platform = typeof platformRaw === 'string' && platformRaw.trim() ? platformRaw.trim().slice(0, 64) : null;
  const mobile = typeof mobileRaw === 'boolean' ? mobileRaw : null;

  const brandsMajor: UaDataBrandMajor[] = [];
  if (Array.isArray(brandsRaw)) {
    for (const b of brandsRaw) {
      const row = safeBrandMajor(b);
      if (row) brandsMajor.push(row);
      if (brandsMajor.length >= 6) break;
    }
  }

  return {
    uach_available: true,
    uaData_platform: platform,
    uaData_mobile: mobile,
    uaData_brands_major: brandsMajor.length ? brandsMajor : null,
  };
}

