export const CITY_AIRPORTS = {
  北京: 'BJS', 上海: 'SHA', 广州: 'CAN', 深圳: 'SZX', 杭州: 'HGH', 成都: 'CTU',
  重庆: 'CKG', 武汉: 'WUH', 南京: 'NKG', 西安: 'XIY', 厦门: 'XMN', 长沙: 'CSX',
};

export const CITY_CATALOG = {
  深圳: {
    center: [22.5431, 114.0579],
    airport: { lat: 22.6393, lng: 113.8107 },
    intro: '从海岸、公园到创意街区，留出时间感受深圳不同的生活节奏。',
    neighborhoods: [
      { name: '福田中心', lat: 22.5407, lng: 114.0596, note: '城市交通枢纽，适合从机场进城后入住。' },
      { name: '南山华侨城', lat: 22.5419, lng: 113.9878, note: '靠近创意园与海岸，三天行程的步行体验更好。' },
      { name: '蛇口海上世界', lat: 22.4845, lng: 113.9182, note: '适合偏爱海边和慢节奏夜生活的旅行。' },
    ],
    places: [
      { id: 'sz-nantou', name: '南头古城', lat: 22.5345, lng: 113.9233, area: '南山', category: '历史街区', duration: 120, description: '在城墙、展览与小店之间慢慢走。', time: 'afternoon' },
      { id: 'sz-oct', name: '华侨城创意文化园', lat: 22.5428, lng: 113.9864, area: '南山', category: '艺术', duration: 150, description: '看展、逛设计小店，适合留一段自由探索时间。', time: 'afternoon' },
      { id: 'sz-bay', name: '深圳湾公园', lat: 22.5160, lng: 113.9440, area: '南山', category: '海岸', duration: 90, description: '沿海散步，看城市天际线和落日。', time: 'evening' },
      { id: 'sz-seaworld', name: '海上世界', lat: 22.4848, lng: 113.9182, area: '蛇口', category: '街区', duration: 100, description: '适合在海边吃晚餐，结束当天的行程。', time: 'evening' },
      { id: 'sz-museum', name: '深圳博物馆', lat: 22.5458, lng: 114.0606, area: '福田', category: '博物馆', duration: 120, description: '从城市历史了解深圳，再去探索它的当下。', time: 'morning' },
      { id: 'sz-lianhuashan', name: '莲花山公园', lat: 22.5560, lng: 114.0614, area: '福田', category: '公园', duration: 90, description: '登上山顶，俯瞰福田中心区。', time: 'morning' },
      { id: 'sz-huaqiangbei', name: '华强北', lat: 22.5457, lng: 114.0885, area: '福田', category: '城市探索', duration: 100, description: '走进电子街区，感受深圳的另一面。', time: 'afternoon' },
      { id: 'sz-baoanbay', name: '欢乐港湾', lat: 22.5527, lng: 113.8794, area: '宝安', category: '海岸', duration: 100, description: '在海滨步道放慢脚步，适合傍晚到访。', time: 'evening' },
      { id: 'sz-dafen', name: '大芬油画村', lat: 22.6142, lng: 114.1362, area: '龙岗', category: '艺术', duration: 130, description: '走访画室与街巷，寻找不一样的艺术角落。', time: 'afternoon' },
      { id: 'sz-gankeng', name: '甘坑古镇', lat: 22.6302, lng: 114.0906, area: '龙岗', category: '历史街区', duration: 120, description: '穿过客家村落与巷道，留意在地生活。', time: 'morning' },
      { id: 'sz-xianhu', name: '仙湖植物园', lat: 22.5817, lng: 114.1727, area: '罗湖', category: '自然', duration: 180, description: '把半天交给植物、湖面与山路。', time: 'morning' },
      { id: 'sz-dameisha', name: '大梅沙海滨公园', lat: 22.5946, lng: 114.3033, area: '盐田', category: '海岸', duration: 150, description: '去更开阔的海岸线，适合天气好的时候。', time: 'afternoon' },
      { id: 'sz-dapeng', name: '大鹏所城', lat: 22.5951, lng: 114.5057, area: '大鹏', category: '历史街区', duration: 180, description: '安排更长的路程，换来与市中心不同的旧城体验。', time: 'morning' },
    ],
  },
};

export const DEFAULT_MEMORY = {
  homeCity: '',
  transportPreference: 'flight',
  pricePriority: true,
  avoidRedEye: true,
  hotelBrands: ['汉庭', '希尔顿'],
  hotelNightBudget: 550,
  diningBudgetPerPerson: 0,
  cuisinePreferences: [],
  visitedCities: [],
  visitedPlaces: [],
  interests: ['海岸', '艺术', '历史街区'],
};
