Component({
  properties: {
    item: {
      type: Object,
      value: {}
    },
    locationName: {
      type: String,
      value: '-'
    },
    color: {
      type: String,
      value: '#00D2FF'
    }
  },
  methods: {
    onTap() {
      const device = this.data.item?.device
      if (!device?.id) return
      wx.navigateTo({
        url: `/pages/health-archive/detail?id=${device.id}&name=${encodeURIComponent(device.name || '')}`,
      })
    }
  }
})
